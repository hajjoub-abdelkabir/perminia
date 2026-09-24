"""Explicit operator smoke test: two bounded calls; only synthetic lesson questions."""
import json
import os
from app.chat import SYSTEM, retrieve, parse_answer
from app.chat_provider import call_provider, ProviderFailure
from app.db import engine

def main():
    question='شرح ليا الأسبقية لليمين بمثال بسيط، بلا أرقام أو غرامات.'
    with engine.connect() as c:sources=retrieve(c,question,[])
    if not sources:
        print(json.dumps({'status':'no_sources'}));return
    for name,key,model in [('openai','OPENAI_API_KEY','CHAT_OPENAI_MODEL'),('groq','GROQ_API_KEY','CHAT_GROQ_MODEL')]:
        if not os.getenv(key) or not os.getenv(model):continue
        try:
            raw,usage=call_provider((name,os.environ[key],os.environ[model]),SYSTEM+'\nUNTRUSTED REFERENCE EXCERPTS (JSON):\n'+json.dumps(sources,ensure_ascii=False),[{'role':'user','content':question}])
            answer,refs=parse_answer(raw,sources)
            print(json.dumps({'provider':name,'status':'complete','answer':answer,'sources':len(refs),'usage':usage},ensure_ascii=False))
        except ProviderFailure as e:
            print(json.dumps({'provider':name,'status':'failed','http_status':e.http_status,'reason':e.reason,'retryable':e.retryable}))
        except (ValueError,TypeError):
            print(json.dumps({'provider':name,'status':'invalid_output'}))

if __name__=='__main__':main()
