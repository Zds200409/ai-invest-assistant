# -*- coding: utf-8 -*-
"""端到端自测：不起外部进程，在脚本内启动服务并验证三个接口。"""
import json
import threading
import time

import requests

import app

PORT = 8011
BASE = 'http://127.0.0.1:%d' % PORT


def start_server():
    from http.server import ThreadingHTTPServer
    srv = ThreadingHTTPServer(('127.0.0.1', PORT), app.Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


def main():
    print('=' * 60)
    print('1) 直接测试 fetch_quote')
    q = app.fetch_quote('600519')
    print('   ok =', q.get('ok'))
    if q.get('ok'):
        print('   名称: %s  代码: %s' % (q['name'], q['symbol']))
        print('   现价: %s  涨跌: %s (%s%%)  振幅: %s%%' % (q['price'], q['change'], q['change_pct'], q['amplitude']))
        print('   成交额: %.2f 亿' % (q['amount'] / 1e8))
    else:
        print('   ERROR:', q.get('error'))

    print()
    print('2) 直接测试 prompt 组装')
    if q.get('ok'):
        prompt = app.build_prompt(q)
        print('   prompt 长度:', len(prompt))
        print('   前 160 字:', prompt[:160].replace('\n', ' | '))

    print()
    print('3) 直接测试 stream_mock（前 5 个分片）')
    if q.get('ok'):
        gen = app.stream_mock(q)
        pieces = []
        for i, p in enumerate(gen):
            pieces.append(p)
            if i >= 4:
                break
        print('   分片样例:', repr(''.join(pieces))[:120])

    print()
    print('4) 启动 HTTP 服务并测试接口')
    srv = start_server()
    time.sleep(0.6)
    try:
        r = requests.get(BASE + '/api/config', timeout=5)
        print('   /api/config ->', r.status_code, r.json())

        r = requests.get(BASE + '/api/quote?code=600519', timeout=8)
        d = r.json()
        print('   /api/quote  ->', r.status_code, 'ok=%s' % d.get('ok'),
              (d.get('name', '') + ' ' + str(d.get('price', ''))) if d.get('ok') else d.get('error'))

        r = requests.get(BASE + '/api/quote?code=abcdef', timeout=8)
        print('   /api/quote(非法) ->', r.status_code, r.json().get('error'))

        # SSE 流式
        r = requests.get(BASE + '/api/analyze?code=600519', stream=True, timeout=20)
        print('   /api/analyze ->', r.status_code, r.headers.get('Content-Type'))
        events, text = 0, ''
        for line in r.iter_lines(decode_unicode=False):
            if not line:
                continue
            s = line.decode('utf-8', 'ignore')
            if s.startswith('data: '):
                obj = json.loads(s[6:])
                events += 1
                if obj['type'] == 'meta':
                    print('      首个事件 meta:', obj)
                elif obj['type'] == 'delta':
                    text += obj['text']
                elif obj['type'] == 'done':
                    print('      收到 done，共 %d 个事件' % events)
                    break
                elif obj['type'] == 'error':
                    print('      ERROR 事件:', obj)
                    break
            if events > 40:
                print('      (截断，已接收 %d 事件)' % events)
                break
        print('   已接收文本前 90 字:', repr(text[:90]))

        # 首页
        r = requests.get(BASE + '/', timeout=5)
        print('   / ->', r.status_code, 'HTML 长度', len(r.text), '| 含标题:', 'AI 投研辅助工作流' in r.text)
    finally:
        srv.shutdown()
        srv.server_close()
        print()
        print('服务已关闭')

    print('=' * 60)
    print('自测完成')


if __name__ == '__main__':
    main()
