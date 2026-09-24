"""Bounded, non-agentic transport. No tools, redirects, retries or arbitrary URLs."""
import json
import os
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

class ProviderFailure(Exception):
    def __init__(self, retryable=False, http_status=None, reason=None):
        self.retryable = retryable
        self.http_status = http_status
        self.reason = reason

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def providers():
    if os.getenv('CHAT_ENABLED') != 'true':
        return []
    result = []
    for name, key, model in [('openai','OPENAI_API_KEY','CHAT_OPENAI_MODEL'),('groq','GROQ_API_KEY','CHAT_GROQ_MODEL')]:
        if name=='openai' and os.getenv('CHAT_OPENAI_ENABLED','true')!='true':
            continue
        if os.getenv(key) and os.getenv(model):
            result.append((name,os.environ[key],os.environ[model]))
    return result

def call_provider(provider, instructions, messages):
    name,key,model = provider
    if name == 'openai':
        url = 'https://api.openai.com/v1/responses'
        body = dict(model=model,store=False,instructions=instructions,input=messages,max_output_tokens=1200)
    else:
        url = 'https://api.groq.com/openai/v1/chat/completions'
        body = dict(model=model,messages=[{'role':'system','content':instructions},*messages],max_completion_tokens=1200,stream=False)
        if model.startswith('openai/gpt-oss-'):
            body['reasoning_effort']='low'
        if model=='qwen/qwen3.8-27b':
            body['reasoning_effort']='none'
    req = Request(url,data=json.dumps(body,ensure_ascii=False).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','User-Agent':'PerminIA/0.1','Accept':'application/json'})
    try:
        with build_opener(NoRedirect()).open(req,timeout=20) as response:
            raw = response.read(131073)
        if len(raw)>131072: raise ProviderFailure()
        data = json.loads(raw)
        if name == 'openai':
            if data.get('status')!='completed': raise ProviderFailure(reason='incomplete_output')
            value = '\n'.join(p['text'] for item in data.get('output',[]) if item.get('type')=='message' for p in item.get('content',[]) if p.get('type')=='output_text')
            usage = data.get('usage',{})
        else:
            item=data['choices'][0]
            if item.get('finish_reason')!='stop': raise ProviderFailure(reason='incomplete_output')
            value=item['message']['content']; u=data.get('usage',{})
            usage={'input_tokens':u.get('prompt_tokens'),'output_tokens':u.get('completion_tokens')}
        return value,usage
    except HTTPError as e:
        # Never expose upstream messages, request bodies or credentials.
        reason=None
        try:
            details=json.loads(e.read(8192)).get('error',{})
            error=details.get('type') if details.get('type')=='insufficient_quota' else details.get('code') or details.get('type')
            if error in ('insufficient_quota','invalid_api_key','rate_limit_exceeded','model_not_found','model_decommissioned'):
                reason=error
        except (ValueError,AttributeError,TypeError):
            pass
        raise ProviderFailure(e.code in (408,429,500,502,503,504),e.code,reason) from None
    except (URLError,TimeoutError,OSError):
        raise ProviderFailure(True) from None
    except (ValueError,KeyError,TypeError,IndexError):
        raise ProviderFailure() from None
