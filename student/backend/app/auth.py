"""First-party student authentication with opaque, server-revocable cookies."""
import hashlib
import hmac
import os
import re
import secrets
import threading

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import engine


class AuthRequestGuard:
    """Bound credential bodies before parsing; never cache any auth response."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not scope['path'].startswith(('/api/v1/chat/','/api/v1/auth/','/api/v1/school','/api/v1/student/journey','/api/v1/student/training')):
            return await self.app(scope, receive, send)

        async def no_store(message):
            if message['type'] == 'http.response.start':
                message['headers'] = [(k, v) for k, v in message['headers'] if k.lower() != b'cache-control']
                message['headers'].append((b'cache-control', b'no-store'))
            await send(message)

        if scope['method'] in ('POST','PUT','PATCH'):
            body = bytearray()
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                body.extend(message.get('body', b''))
                if len(body) > (131072 if scope['path'].startswith('/api/v1/student/journey') else 8192):
                    from fastapi.responses import JSONResponse
                    return await JSONResponse(status_code=413, content={'detail': 'Request too large'})(scope, receive, no_store)
                if not message.get('more_body', False):
                    break
            delivered = False

            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
                return await receive()

            return await self.app(scope, bounded_receive, no_store)
        return await self.app(scope, receive, no_store)


router = APIRouter(prefix='/api/v1/auth', tags=['Student account'])
COOKIE = 'sya9a_student_session'
ORIGINS = frozenset(os.environ.get('STUDENT_ALLOWED_ORIGINS', 'http://localhost:5174,http://127.0.0.1:5174').split(','))
SECURE = os.environ.get('STUDENT_COOKIE_SECURE', 'true') == 'true'
# Bound password hashing memory under concurrent login attempts (32 MiB each).
HASH_SLOTS = threading.BoundedSemaphore(2)


def password_hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    with HASH_SLOTS:
        result = hashlib.scrypt(password.encode('utf-8'), salt=salt, n=32768, r=8, p=3, maxmem=64*1024*1024, dklen=32)
    return 'scrypt-v1$' + salt.hex() + '$' + result.hex()


def password_matches(password, encoded):
    try:
        kind, salt, digest = encoded.split('$')
        if kind != 'scrypt-v1':
            return False
        return hmac.compare_digest(password_hash(password, bytes.fromhex(salt)), encoded)
    except (ValueError, TypeError):
        return False


DUMMY_HASH = password_hash('unused-password-for-timing-only')


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


class LoginInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}", value):
            raise ValueError('دخل بريد إلكتروني صحيح.')
        return value


class RegisterInput(LoginInput):
    password: str = Field(min_length=12, max_length=128)
    display_name: str = Field(min_length=2, max_length=80)

    @field_validator('display_name')
    @classmethod
    def normalize_name(cls, value):
        value = value.strip()
        if len(value) < 2 or any(ord(c) < 32 for c in value):
            raise ValueError('دخل الاسم اللي بغيتي يبان فحسابك.')
        return value


class ActivationInput(RegisterInput):
    invitation_code: str = Field(min_length=43, max_length=43, pattern=r'^[A-Za-z0-9_-]{43}$')


def protect_mutation(request: Request):
    # Require a custom header AND an exact trusted Origin; no permissive CORS.
    if request.headers.get('origin') not in ORIGINS or request.headers.get('x-sya9a-request') != 'student':
        raise HTTPException(403, 'هاد الطلب ما مسموحش به من هاد الصفحة.')


def limit_login(request, email, action):
    # Ignore untrusted X-Forwarded-For. In local Compose the proxy IP budget is shared.
    client = request.client.host if request.client else 'unknown'
    checks = [(f'{action}:email:{email}', 10), (f'{action}:ip:{client}', 60)]
    with engine.begin() as connection:
        allowed = [connection.execute(text('SELECT identity.auth_rate_limit(:bucket,:cap)'),
                   {'bucket': token_hash(key), 'cap': cap}).scalar_one() for key, cap in checks]
    if not all(allowed):
        raise HTTPException(429, 'حاولتي بزاف فمدة قصيرة. تسنّى شوية وعاود جرّب.', headers={'Retry-After': '900'})


def set_session(response, token):
    response.set_cookie(COOKIE, token, max_age=7*24*3600, httponly=True, secure=SECURE, samesite='strict', path='/api')
    response.headers['Cache-Control'] = 'no-store'


def read_user(token):
    if not token or len(token) > 128:
        return None
    with engine.connect() as connection:
        row = connection.execute(text('SELECT * FROM identity.portal_session(:hash)'), {'hash': token_hash(token)}).mappings().first()
    return dict(row) if row else None


def require_account(request: Request):
    user = read_user(request.cookies.get(COOKIE))
    if not user:
        raise HTTPException(401, 'خاصك تدخل للحساب ديالك باش تكمل.')
    return user


def require_student(user=Depends(require_account)):
    if user['role'] != 'student':
        raise HTTPException(403, 'هاد الفضاء خاص بالتلميذ.')
    return user


def require_school_student(user=Depends(require_student)):
    if not user['school_id']:
        raise HTTPException(403, 'الحساب ديالك باقي ما مربوطش بمدرسة.')
    return user


@router.get('/me')
def me(response: Response, user=Depends(require_account)):
    response.headers['Cache-Control'] = 'no-store'
    return {'user': user}


@router.post('/register', dependencies=[Depends(protect_mutation)], deprecated=True)
def register():
    raise HTTPException(410, 'التسجيل المفتوح تسدّ. خاصك دعوة خاصة باش تفعّل حسابك مع المدرسة.')


@router.post('/activate', status_code=201, dependencies=[Depends(protect_mutation)])
def activate(body: ActivationInput, request: Request, response: Response):
    limit_login(request, body.email, 'activate')
    encoded = password_hash(body.password)
    token = secrets.token_urlsafe(32)
    try:
        with engine.begin() as connection:
            member = connection.execute(text('SELECT identity.auth_activate(:invite,:email,:name,:password,:token)'),
                {'invite': token_hash(body.invitation_code), 'email': body.email, 'name': body.display_name,
                 'password': encoded, 'token': token_hash(token)}).scalar_one()
            if member is None:
                raise HTTPException(400, 'الدعوة ما صالحةش لهاد البريد، أو سالا وقتها، أو تستعملات. تواصل مع المدرسة.')
    except IntegrityError:
        raise HTTPException(409, 'ما قدرناش ننشئو الحساب بهاد المعطيات. إلا عندك حساب، جرّب تسجيل الدخول.') from None
    set_session(response, token)
    return {'user': read_user(token)}


@router.post('/login', dependencies=[Depends(protect_mutation)])
def login(body: LoginInput, request: Request, response: Response):
    limit_login(request, body.email, 'login')
    with engine.connect() as connection:
        credentials = connection.execute(text('SELECT * FROM identity.portal_credentials(:email)'), {'email': body.email}).mappings().first()
    valid = password_matches(body.password, credentials['password_hash'] if credentials else DUMMY_HASH)
    if not valid or not credentials:
        raise HTTPException(401, 'البريد الإلكتروني أو كلمة السر ما صحيحاش.')
    token = secrets.token_urlsafe(32)
    with engine.begin() as connection:
        created = connection.execute(text('SELECT identity.portal_new_session(:member,:token,:expected)'),
                           {'member': credentials['membership_id'], 'token': token_hash(token), 'expected': credentials['password_hash']}).scalar_one()
        if not created:
            raise HTTPException(401, 'تبدلات معلومات الدخول. عاود دخل للحساب.')
        old_token = request.cookies.get(COOKIE)
        if old_token:
            connection.execute(text('SELECT identity.auth_logout(:hash)'), {'hash': token_hash(old_token)})
    set_session(response, token)
    return {'user': read_user(token)}


@router.post('/logout', dependencies=[Depends(protect_mutation)])
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        with engine.begin() as connection:
            connection.execute(text('SELECT identity.auth_logout(:hash)'), {'hash': token_hash(token)})
    response.delete_cookie(COOKIE, path='/api', secure=SECURE, httponly=True, samesite='strict')
    response.headers['Cache-Control'] = 'no-store'
    return {'status': 'signed_out'}


class RecoveryInput(LoginInput):
    password: str = Field(min_length=12,max_length=128)
    recovery_code: str = Field(min_length=43,max_length=43,pattern=r'^[A-Za-z0-9_-]{43}$')

@router.post('/recover',dependencies=[Depends(protect_mutation)])
def recover(body:RecoveryInput,request:Request,response:Response):
    limit_login(request,body.email,'recover')
    encoded=password_hash(body.password)
    with engine.begin() as c:
        ok=c.execute(text('SELECT identity.redeem_account_recovery(:hash,:email,:password)'),
          {'hash':token_hash(body.recovery_code),'email':body.email,'password':encoded}).scalar_one()
        if not ok:raise HTTPException(400,'الرمز ما صالحش لهاد الحساب، تسالا وقتو أو تستعمل. تواصل مع المدرسة.')
    response.delete_cookie(COOKIE,path='/api',secure=SECURE,httponly=True,samesite='strict')
    return {'saved':True}
