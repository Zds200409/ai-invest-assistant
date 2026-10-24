# -*- coding: utf-8 -*-
"""测试真实大模型调用链路（读取 .env 中的配置）。"""
import sys
import time

import app

print('=' * 60)
print('配置检查')
print('  模型     :', app.LLM_MODEL)
print('  Base URL :', app.LLM_BASE_URL)
print('  Key 是否加载:', '是（长度 %d，前缀 %s…）' % (len(app.LLM_API_KEY), app.LLM_API_KEY[:8]) if app.LLM_API_KEY else '否')

if not app.LLM_API_KEY:
    print('\n未读到 API Key，请检查 .env 文件')
    sys.exit(1)

print()
print('步 1：抓取行情')
q = app.fetch_quote('600519')
if not q.get('ok'):
    print('  行情失败:', q.get('error'))
    sys.exit(1)
print('  %s %s  现价 %s  涨跌 %s%%' % (q['name'], q['symbol'].upper(), q['price'], q['change_pct']))

print()
print('步 2：组装 Prompt（%d 字符）' % len(app.build_prompt(q)))

print()
print('步 3：调用大模型（流式）')
print('-' * 60)
t0 = time.time()
first_at = None
chunks = 0
text = ''
try:
    for piece in app.stream_llm(app.build_prompt(q)):
        if first_at is None:
            first_at = time.time() - t0
        chunks += 1
        text += piece
        print(piece, end='', flush=True)
except Exception as exc:
    print('\n\n[调用失败] %s: %s' % (type(exc).__name__, exc))
    sys.exit(1)
elapsed = time.time() - t0
print('-' * 60)
print()
print('结果统计')
print('  首字延迟 : %.2f 秒' % (first_at or 0))
print('  总耗时   : %.2f 秒' % elapsed)
print('  分片数量 : %d' % chunks)
print('  总字数   : %d' % len(text))
print('  含风险提示:', '不构成投资建议' in text)
print('=' * 60)
