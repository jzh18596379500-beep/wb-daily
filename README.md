# WorkBuddy 每日积分（GitHub Actions 版）

每天北京时间 08:10，GitHub 的服务器替你跑一次：签到 + 派猫猫 + 开盲盒。你的电脑关不关机都不影响。

## 三步部署

**1. 建仓库**

在 GitHub 新建一个**私有**仓库，把这几个文件传上去（保持目录结构）：

```
wb_daily.py
.github/workflows/daily.yml
```

**2. 拿到 token**

1. 浏览器打开 https://www.workbuddy.cn 并确认已登录
2. F12 打开开发者工具 → Network → 刷新页面
3. 随便点一个 `/v2/` 开头的请求，看 Request Headers 里的
   `Authorization: Bearer eyJxxxx...`
4. 复制 `Bearer ` 后面那一长串（脚本会自动去掉 `Bearer ` 前缀，带着复制也行）

也可以 F12 → Console 里执行，直接从本地存储取：

```js
(()=>{for(const s of [localStorage,sessionStorage]){for(const k of ["accessToken","access_token","token"]){const v=s.getItem(k);if(v&&v.startsWith("eyJ")){copy(v);console.log("已复制");return}}}})()
```

**3. 填 Secrets**

仓库 → Settings → Secrets and variables → Actions → **New repository secret**

- Name: `WB_TOKEN`
- Secret: 粘贴上一步的 token

然后去 Actions 页，点 `WorkBuddy daily credits` → `Run workflow` 手动跑一次，看日志里有没有"签到成功"。

## 日常

- 跑不跑成，Actions 里都能看到日志，失败了会显示具体原因。
- 想改时间，改 `daily.yml` 里的 cron。记住是 UTC：北京时间 8:00 = UTC 0:00。
- 想换国际版域名，在 Settings → Variables 里加一个 `WB_DOMAIN`（比如 `www.codebuddy.ai`），不加默认 `www.workbuddy.cn`。

## token 过期了

表现：日志里出现 `401 未授权` 或 `签到失败：...`。

处理：重新走一遍上面第 2、3 步，把新的 token 覆盖掉旧的 Secret。不用改代码。

## 两个已知坑

1. **GitHub 会在仓库 60 天无任何提交后自动暂停 schedule。** 随便提交点东西（哪怕改个空格）就能恢复。
2. **定时不精确。** GitHub 的免费 runner 是排队制的，说好 8:10 可能 8:40 才跑。领积分不急，无所谓。

## 安全提醒

- token 等于你的登录凭证，只能放进私有仓库的 Secrets，别提交到代码里、别发给别人。
- 这是对你自己账号做自动化，属于灰色地带；官方如果调整规则，可能出现限权或积分回收。

## 本地试跑（可选）

```bash
WB_TOKEN=eyJ... python wb_daily.py --dry-run   # 只看，不提交
WB_TOKEN=eyJ... python wb_daily.py             # 真跑
```
