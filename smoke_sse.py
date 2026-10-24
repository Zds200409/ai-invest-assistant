# -*- coding: utf-8 -*-
"""对已启动的服务做一次完整 SSE 冒烟测试。"""
import json

import requests

BASE = 'http://127.0.0.1:8000'

print('服务状态:', requests.get(BASE + '/api/config', timeout=5).json())

r = requests.get(BASE + '/api/analyze?code=600519', stream=True, timeout=60)
print('SSE 状态:', r.status_code, '|', r.headers.get('Content-Type'))
print('-' * 60)

text = ''
saw_final = False
violations = []
for line in r.iter_lines(decode_unicode=False):
    if not line:
        continue
    s = line.decode('utf-8', 'ignore')
    if not s.startswith('data: '):
        continue
    obj = json.loads(s[6:])
    if obj['type'] == 'delta':
        text += obj['text']
        print(obj['text'], end='', flush=True)
    elif obj['type'] == 'final':
        saw_final = True
        violations = obj.get('violations', [])
        break
    elif obj['type'] == 'done':
        break
    elif obj['type'] == 'error':
        print('\n[ERROR]', obj.get('message'))
        break

print()
print('-' * 60)
print('流式文本长度:', len(text))
print('触发校验层:', saw_final)
if violations:
    for v in violations:
        print('  已过滤 [%s]: %s' % (v['reason'], v['text']))
