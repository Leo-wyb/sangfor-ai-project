import json, sys, time, urllib.request, http.cookiejar
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = 'http://127.0.0.1:8642'
SUF = str(int(time.time()))[-5:]
UNIQ1 = 'tester01' + SUF
UNIQ2 = 'tester02' + SUF
UNIQ3 = '粉丝' + SUF
passed, failed = 0, 0

def check(name, cond, detail=''):
    global passed, failed
    mark = 'PASS' if cond else 'FAIL'
    if cond: passed += 1
    else: failed += 1
    print(f'[{mark}] {name}' + (f'  -> {detail}' if detail and not cond else ''))

def client():
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

def post(op, path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    try:
        with op.open(req) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())

def get(op, path):
    req = urllib.request.Request(BASE + path)
    try:
        with op.open(req) as r:
            return r.status, r.read().decode('utf-8', 'replace'), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace'), e.geturl()

# 1. 首页未登录 → 返回登录页 200
op = client()
s, body, _ = get(op, '/')
check('GET / 未登录返回登录页', s == 200 and '登录以进入项目展示' in body)

# 2. 未登录访问 home.html → 重定向
s, body, final = get(op, '/home.html')
check('未登录访问 /home.html 被重定向', s == 200 and final.endswith('/') and '登录以进入项目展示' in body, f's={s} url={final}')

# 3. /api/me 未登录 → 401
import urllib.error
def get_json(op, path):
    req = urllib.request.Request(BASE + path)
    try:
        with op.open(req) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())
s, data = get_json(op, '/api/me')
check('未登录 /api/me 返回 401', s == 401 and data.get('ok') is False)

# 4. 错误密码登录 → 401
s, data = post(op, '/api/login', {'username': 'admin', 'password': 'wrong'})
check('错误密码登录被拒绝', s == 401 and data.get('ok') is False and '错误' in data.get('message', ''))

# 5. admin/admin 登录成功 → 200 + cookie
s, data = post(op, '/api/login', {'username': 'admin', 'password': 'admin'})
check('admin/admin 登录成功', s == 200 and data.get('ok') is True and data.get('username') == 'admin')

# 6. 登录后 /api/me → admin
s, data = get_json(op, '/api/me')
check('登录后 /api/me 返回用户名', s == 200 and data.get('username') == 'admin')

# 7. 登录后访问 home.html → 200 且含页面内容
s, body, _ = get(op, '/home.html')
check('登录后可访问 home.html', s == 200 and 'CyberNWT' in body)

# 8. 登录后再访问 / → 重定向到 home.html（已登录免重复登录）
s, body, final = get(op, '/')
check('已登录访问 / 跳转 home.html', final.endswith('/home.html'), f'url={final}')

# 9. 注册新用户 → 成功
op2 = client()
s, data = post(op2, '/api/register', {'username': UNIQ1, 'password': 'test123456'})
check('注册新用户成功', s == 200 and data.get('ok') is True)

# 10. 重复注册 → 409
s, data = post(op2, '/api/register', {'username': UNIQ1, 'password': 'test123456'})
check('重复注册被拒绝', s == 409 and '已被注册' in data.get('message', ''))

# 11. 非法用户名 → 400
s, data = post(op2, '/api/register', {'username': 'a', 'password': 'test123456'})
check('过短用户名被拒绝', s == 400)
s, data = post(op2, '/api/register', {'username': 'bad name!', 'password': 'test123456'})
check('非法字符用户名被拒绝', s == 400)
s, data = post(op2, '/api/register', {'username': UNIQ2, 'password': '123'})
check('过短密码被拒绝', s == 400)

# 12. 新用户登录 → 成功
s, data = post(op2, '/api/login', {'username': UNIQ1, 'password': 'test123456'})
check('新注册用户可登录', s == 200 and data.get('ok') is True)

# 13. 中文用户名注册+登录
op3 = client()
s, data = post(op3, '/api/register', {'username': UNIQ3, 'password': 'test123456'})
check('中文用户名注册成功', s == 200 and data.get('ok') is True)
s, data = post(op3, '/api/login', {'username': UNIQ3, 'password': 'test123456'})
check('中文用户名可登录', s == 200 and data.get('ok') is True)

# 14. 退出登录 → /api/me 恢复 401
s, data = post(op, '/api/logout', {})
check('退出登录成功', s == 200 and data.get('ok') is True)
s, data = get_json(op, '/api/me')
check('退出后 /api/me 返回 401', s == 401)

print()
print(f'结果: {passed} 通过, {failed} 失败')
sys.exit(1 if failed else 0)
