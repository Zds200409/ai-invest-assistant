# -*- coding: utf-8 -*-
"""测试输出校验层：先单元验证规则，再跑一次真实 LLM + 校验的完整路径。"""
import app

print('=' * 60)
print('单元测试：sanitize_output')

cases = [
    ('该股今日上涨1.25%，振幅2.57%。', 0),
    ('较昨日收盘价上涨16.51元，显示上涨动力。', 0),                    # 有数据支撑，应放行
    ('今日成交量57686手，成交额76.77亿元，较昨日有所增加。', 1),        # 无量能基准，应拦截
    ('相比去年同比增长明显。', 1),
    ('今日放量上攻，资金流入明显。', 1),
    ('收盘价站上20日均线。', 1),
]
for text, expect in cases:
    clean, viol = app.sanitize_output(text)
    flag = 'OK ' if len(viol) == expect else 'FAIL'
    print('  [%s] 过滤 %d 处（预期 %d）' % (flag, len(viol), expect))
    print('       原文:', text)
    print('       清洗:', clean if clean else '（整段被过滤）')
    for v in viol:
        print('       命中:', v['reason'], '->', v['text'])

print()
print('=' * 60)
print('真实链路：行情 → Prompt → 模型 → 校验')

q = app.fetch_quote('600519')
if not q.get('ok'):
    print('行情失败:', q.get('error'))
    raise SystemExit(1)

raw = ''.join(app.stream_llm(app.build_prompt(q)))
clean, violations = app.sanitize_output(raw)

print('原始输出 %d 字，清洗后 %d 字' % (len(raw), len(clean)))
print()
print('--- 原始输出 ---')
print(raw)
print()
print('--- 清洗后输出 ---')
print(clean)
print()
print('--- 过滤统计 ---')
if violations:
    for v in violations:
        print('  · [%s] %s' % (v['reason'], v['text']))
else:
    print('  本次模型未编造，无需过滤')
print('=' * 60)
