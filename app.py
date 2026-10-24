# -*- coding: utf-8 -*-
"""
AI 投研辅助工作流（演示项目）

流程：输入股票代码 → 抓取实时行情 → 组装结构化 Prompt → 大模型流式生成盘面解读 → 前端打字机输出

启动：
    python app.py
然后浏览器打开 http://127.0.0.1:8000

LLM 配置（环境变量，不配置则自动进入演示模式）：
    LLM_BASE_URL   默认 https://open.bigmodel.cn/api/paas/v4   （智谱）
    LLM_API_KEY    你的 API Key
    LLM_MODEL      默认 glm-4-flash（智谱免费模型）

其他可选：
    PORT           默认 8000
"""
import json
import os
import re
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_dotenv():
    """极简 .env 加载器：把同目录 .env 里的 KEY=VALUE 注入环境变量。
    已存在的环境变量优先，不会被覆盖。"""
    path = os.path.join(BASE_DIR, '.env')
    if not os.path.isfile(path):
        return
    with open(path, encoding='utf-8') as fp:
        for raw in fp:
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, val = line.split('=', 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, val)


load_dotenv()

PORT = int(os.environ.get('PORT', '8000'))

# ── LLM 配置 ────────────────────────────────────────────────────────────────
LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://open.bigmodel.cn/api/paas/v4')
LLM_API_KEY = os.environ.get('LLM_API_KEY', '').strip()
LLM_MODEL = os.environ.get('LLM_MODEL', 'glm-4-flash')

SINA_HEADERS = {
    'Referer': 'https://finance.sina.com.cn',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
}


# ── 行情抓取 ────────────────────────────────────────────────────────────────
def normalize_code(code):
    """把用户输入规整成 sh600519 / sz000001 形式。"""
    m = re.search(r'(\d{6})', code or '')
    if not m:
        return None
    num = m.group(1)
    if num.startswith(('600', '601', '603', '605', '688', '689')):
        return 'sh' + num
    if num.startswith(('000', '001', '002', '003', '300', '301')):
        return 'sz' + num
    return None


def fetch_quote(code):
    """从新浪免费行情接口取实时数据（无需 API Key）。"""
    symbol = normalize_code(code)
    if not symbol:
        return {'ok': False, 'error': '股票代码格式不对，请输入 6 位数字，例如 600519'}

    try:
        resp = requests.get('https://hq.sinajs.cn/list=' + symbol,
                            headers=SINA_HEADERS, timeout=8)
        resp.encoding = 'gbk'
    except Exception as exc:
        return {'ok': False, 'error': '行情接口请求失败：%s' % exc}

    if '="' not in resp.text:
        return {'ok': False, 'error': '未查到该代码的行情，可能不是有效的 A 股代码'}

    raw = resp.text.split('="', 1)[1].split('";', 1)[0]
    f = raw.split(',')
    if len(f) < 32 or not f[0]:
        return {'ok': False, 'error': '行情数据格式异常，请稍后重试'}

    def num(idx):
        try:
            return float(f[idx])
        except (ValueError, IndexError):
            return 0.0

    name, open_p, prev_close, price, high, low = f[0], num(1), num(2), num(3), num(4), num(5)
    volume, amount = num(8), num(9)

    change = price - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0.0
    amplitude = ((high - low) / prev_close * 100) if prev_close else 0.0

    return {
        'ok': True,
        'symbol': symbol,
        'name': name,
        'date': f[30],
        'time': f[31],
        'open': open_p,
        'prev_close': prev_close,
        'price': price,
        'high': high,
        'low': low,
        'volume': volume,
        'amount': amount,
        'change': round(change, 2),
        'change_pct': round(change_pct, 2),
        'amplitude': round(amplitude, 2),
    }


# ── Prompt 组装 ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    '你是一名谨慎的 A 股投研助理。你只依据用户提供的行情数据做客观解读，'
    '不编造未提供的财务数据、公告或消息面信息。语气专业、克制。'
)


def build_prompt(q):
    return (
        '请基于以下 A 股实时行情数据，输出一段简洁的盘面解读。\n\n'
        '【行情数据】\n'
        '股票：%s（%s）\n'
        '数据时间：%s %s\n'
        '当前价：%s\n'
        '昨收：%s\n'
        '今开：%s\n'
        '最高：%s\n'
        '最低：%s\n'
        '涨跌：%s（%s%%）\n'
        '振幅：%s%%\n'
        '成交量：%.0f 手\n'
        '成交额：%.2f 亿元\n\n'
        '【输出要求】\n'
        '1. 分三段，每段不超过 2 句话，依次为：走势概况 / 值得关注的点 / 风险提示。\n'
        '2. 只能使用上面【行情数据】中明确给出的字段进行描述。以下内容一律不得出现：\n'
        '   - 与昨日、前一日、历史行情的对比或趋势判断（未提供历史数据）\n'
        '   - 成交量放大 / 萎缩 / 资金流入流出等推断（未提供历史量能基准）\n'
        '   - 财务数据、业绩预期、公告、政策、消息面（均未提供）\n'
        '3. 若某项判断缺少数据支撑，请直接说明"该信息未提供"，不要补全。\n'
        '4. 结尾固定加一句：以上内容由 AI 生成，不构成投资建议。\n'
        % (
            q['name'], q['symbol'].upper(), q['date'], q['time'],
            q['price'], q['prev_close'], q['open'], q['high'], q['low'],
            q['change'], q['change_pct'], q['amplitude'],
            q['volume'] / 100.0, q['amount'] / 1e8,
        )
    )


# ── LLM 流式输出 ────────────────────────────────────────────────────────────
def stream_llm(prompt):
    """调用 OpenAI 兼容接口，逐块产出文本。"""
    from openai import OpenAI

    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': prompt},
        ],
        stream=True,
        temperature=0.3,
    )
    for chunk in resp:
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def stream_mock(q):
    """未配置 API Key 时的演示流，用于验证整条链路是否通畅。"""
    text = (
        '【演示模式】未检测到 LLM_API_KEY，以下为模拟输出，用于验证链路是否通畅。\n\n'
        '走势概况：%s 当前价 %s，相对昨收 %s%%，当日振幅 %s%%，'
        '盘中最高 %s、最低 %s，整体波动处于可观察区间。\n\n'
        '值得关注的点：成交额约 %.2f 亿元，量能是判断当日资金参与度的关键；'
        '若价格在放量下上行，说明买盘承接较好，反之需留意冲高回落。\n\n'
        '风险提示：单日行情受消息面与大盘情绪影响较大，请结合更长周期趋势判断，'
        '避免仅凭一日数据做决策。\n\n'
        '以上内容由 AI 生成，不构成投资建议。'
        % (
            q['name'], q['price'], q['change_pct'], q['amplitude'],
            q['high'], q['low'], q['amount'] / 1e8,
        )
    )
    for ch in text:
        yield ch
        time.sleep(0.012)


# ── 输出校验层 ──────────────────────────────────────────────────────────────
# 实测结论：仅靠 Prompt 约束，模型仍会编造"未提供的历史对比"（如拿当日成交量与昨日比较）。
# 因此在流式输出结束后追加一层规则校验，过滤无数据支撑的表述并显式告知用户。
#
# 注意：只拦截"没有数据支撑"的表述，不搞一刀切。
# 例如「较昨日收盘价上涨 16.51 元」是有依据的（Prompt 里给了昨收价），必须放行；
# 而「成交量较昨日增加」无依据（只给了当日成交量），必须拦截。
BANNED_PATTERNS = [
    (r'(成交量|成交额|量能|换手率)[^。！？]{0,15}(较(昨|前)一?日|环比|同比|放大|萎缩|增加|减少)',
     '成交量的历史对比（未提供历史数据）'),
    (r'(较(昨|前)一?日|环比|同比)[^。！？]{0,15}(成交量|成交额|量能|换手率)',
     '成交量的历史对比（未提供历史数据）'),
    (r'放量|缩量', '量能趋势推断（未提供历史量能基准）'),
    (r'同比|环比', '跨期对比（未提供历史数据）'),
    (r'资金(流入|流出)', '资金流向推断（未提供资金数据）'),
    (r'均线|MACD|RSI|KDJ|布林', '技术指标推断（未提供指标数据）'),
]


def sanitize_output(text):
    """过滤掉包含无数据支撑表述的句子，返回（清洗后文本, 被过滤项列表）。"""
    violations = []
    sentences = re.split(r'(?<=[。！？\n])', text)
    kept = []
    for sentence in sentences:
        hit = None
        for pattern, label in BANNED_PATTERNS:
            if re.search(pattern, sentence):
                hit = label
                break
        if hit and len(sentence.strip()) > 4:
            violations.append({'reason': hit, 'text': sentence.strip()})
        else:
            kept.append(sentence)
    return ''.join(kept).strip(), violations


# ── HTTP 服务 ───────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    server_version = 'AIInvestDemo/1.0'

    def log_message(self, fmt, *args):  # 静默默认日志，只保留自定义输出
        print('[%s] %s' % (time.strftime('%H:%M:%S'), fmt % args))

    def _send_json(self, obj, status=200):
        payload = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_file(self, rel_path, content_type):
        path = os.path.join(BASE_DIR, rel_path)
        if not os.path.isfile(path):
            self._send_json({'ok': False, 'error': '文件不存在: ' + rel_path}, 404)
            return
        with open(path, 'rb') as fp:
            payload = fp.read()
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path in ('/', '/index.html'):
            self._send_file(os.path.join('static', 'index.html'), 'text/html; charset=utf-8')
            return

        if path == '/api/quote':
            code = query.get('code', [''])[0]
            self._send_json(fetch_quote(code))
            return

        if path == '/api/config':
            self._send_json({
                'llm_configured': bool(LLM_API_KEY),
                'model': LLM_MODEL,
                'base_url': LLM_BASE_URL,
            })
            return

        if path == '/api/analyze':
            self._handle_analyze(query.get('code', [''])[0])
            return

        self._send_json({'ok': False, 'error': 'Not Found'}, 404)

    def _handle_analyze(self, code):
        quote = fetch_quote(code)
        if not quote.get('ok'):
            self._send_json(quote, 400)
            return

        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Accel-Buffering', 'no')
        self.end_headers()

        def emit(obj):
            self.wfile.write(('data: ' + json.dumps(obj, ensure_ascii=False) + '\n\n').encode('utf-8'))
            self.wfile.flush()

        mode = 'llm' if LLM_API_KEY else 'mock'
        emit({'type': 'meta', 'mode': mode, 'model': LLM_MODEL if mode == 'llm' else 'mock'})

        prompt = build_prompt(quote)
        collected = []
        try:
            gen = stream_llm(prompt) if mode == 'llm' else stream_mock(quote)
            for piece in gen:
                collected.append(piece)
                emit({'type': 'delta', 'text': piece})

            # 输出校验层：过滤无数据支撑的表述
            clean, violations = sanitize_output(''.join(collected))
            if violations:
                emit({'type': 'final', 'text': clean, 'violations': violations})
                print('  已过滤 %d 处无数据支撑的表述' % len(violations))
            else:
                emit({'type': 'done'})
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # 客户端主动断开（如刷新页面），属正常情况，静默退出
            print('  客户端断开连接，已中止本次流式输出')
            return
        except Exception as exc:
            try:
                emit({'type': 'error', 'message': '%s: %s' % (type(exc).__name__, exc)})
            except Exception:
                pass
        return


def main():
    print('=' * 56)
    print('AI 投研辅助工作流')
    print('  地址      : http://127.0.0.1:%d' % PORT)
    print('  LLM 模式  : %s' % ('已配置（%s）' % LLM_MODEL if LLM_API_KEY else '演示模式（未配置 LLM_API_KEY）'))
    print('=' * 56)
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止')
        server.server_close()


if __name__ == '__main__':
    main()
