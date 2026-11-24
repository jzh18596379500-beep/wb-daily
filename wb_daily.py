#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WorkBuddy 每日积分 —— GitHub Actions 版（纯 Python 标准库）。

做三件事：签到、派猫猫/领旅行奖励、开盲盒。
token 只从环境变量 WB_TOKEN 读取，不打印、不落盘。

用法：
  WB_TOKEN=xxx python wb_daily.py
  python wb_daily.py --dry-run      # 只查询，不提交任何写请求
  python wb_daily.py --json         # 机器可读输出
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_DOMAIN = "www.workbuddy.cn"

PATHS = {
    "status": "/v2/billing/meter/checkin-activity-status",
    "checkin": "/v2/billing/meter/daily-checkin",
    "travel_status": "/activity/growth/buddy/travel/status",
    "travel_config": "/activity/growth/buddy/travel/config",
    "travel_claim": "/activity/growth/buddy/travel/claim",
    "travel_depart": "/activity/growth/buddy/travel/depart",
    "energy": "/activity/growth/energy",
    "quota": "/activity/growth/buddy/quota",
    "open": "/activity/growth/buddy/open",
}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


class ApiError(Exception):
    pass


def call(domain, token, path, method="POST", payload=None, timeout=20):
    """发一次请求，返回 (status, dict)。网络异常不抛栈。"""
    url = "https://" + domain + path
    body = None
    if method == "POST":
        body = json.dumps(payload if payload is not None else {},
                          ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/plain, */*")
    req.add_header("User-Agent", UA)
    req.add_header("Origin", "https://" + domain)
    req.add_header("Referer", "https://" + domain + "/")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", "replace")
            return exc.code, (json.loads(raw) if raw else {})
        except Exception:
            return exc.code, {"msg": "HTTP %s" % exc.code}
    except Exception as exc:  # noqa: BLE001
        return 0, {"msg": str(exc)}


def data_of(status, body):
    """取 data 字段；失败抛 ApiError（带可读原因）。"""
    if status == 200 and isinstance(body, dict) and body.get("code") == 0:
        data = body.get("data")
        return data if isinstance(data, dict) else {}
    msg = ""
    if isinstance(body, dict):
        msg = body.get("msg") or body.get("message") or ""
    if status == 401:
        msg = msg or "401 未授权，token 可能已过期"
    raise ApiError(msg or ("HTTP %s" % status))


def pick_location(cfg):
    """从旅行配置里尽量找一个可用地点 id。"""
    if not isinstance(cfg, dict):
        return None
    for key in ("locations", "list", "items", "spots"):
        arr = cfg.get(key)
        if isinstance(arr, list) and arr:
            for item in arr:
                if isinstance(item, dict):
                    for k in ("id", "location_id", "locationId"):
                        if isinstance(item.get(k), int):
                            return item[k]
    for k in ("default_location_id", "location_id", "locationId"):
        if isinstance(cfg.get(k), int):
            return cfg[k]
    return None


def do_checkin(domain, token, dry):
    st, body = call(domain, token, PATHS["status"])
    data = data_of(st, body)
    if data.get("today_checked_in"):
        return {"ok": True, "message": "今日已签到，跳过"}
    if dry:
        return {"ok": True, "message": "今日未签到（预览，未提交）"}
    st, body = call(domain, token, PATHS["checkin"])
    data_of(st, body)
    return {"ok": True, "message": "签到成功"}


def do_travel(domain, token, dry):
    st, body = call(domain, token, PATHS["travel_status"], method="GET")
    data = data_of(st, body)
    state = data.get("state")
    if isinstance(state, dict):
        state = state.get("state") or state.get("status")
    log = []
    if state == "arrived":
        if dry:
            log.append("已到达（预览，未领取）")
        else:
            st, body = call(domain, token, PATHS["travel_claim"])
            data_of(st, body)
            log.append("已领取到达奖励")
            state = "idle"
    if state == "idle":
        loc = None
        try:
            st, body = call(domain, token, PATHS["travel_config"], method="GET")
            loc = pick_location(data_of(st, body))
        except ApiError:
            loc = None
        if loc is None:
            log.append("未取到可用地点，跳过派遣")
        elif dry:
            log.append("空闲（预览，未派遣）")
        else:
            st, body = call(domain, token, PATHS["travel_depart"],
                            payload={"location_id": loc})
            data_of(st, body)
            log.append("已派遣")
    return {"state": state, "log": log or ["状态：%s" % (state or "未知")]}


def do_box(domain, token, dry, max_box):
    st, body = call(domain, token, PATHS["energy"], method="GET")
    energy = data_of(st, body).get("balance")
    st, body = call(domain, token, PATHS["quota"], method="GET")
    cost = data_of(st, body).get("cost_per_open") or 10
    try:
        energy_i, cost_i = int(energy), int(cost)
    except Exception:
        return {"message": "读不到能量或单价，跳过"}
    affordable = max(0, energy_i // cost_i)
    if affordable <= 0:
        return {"message": "能量 %s / 每次 %s，不够开一次，跳过" % (energy, cost)}
    count = min(int(max_box), affordable)
    if dry:
        return {"message": "[预览] 够开 %d 次，计划开 %d 个" % (affordable, count)}
    st, body = call(domain, token, PATHS["open"], payload={"count": count})
    d = data_of(st, body)
    items = d.get("buddies") or d.get("list") or d.get("items")
    opened = len(items) if isinstance(items, list) else count
    return {"message": "开了 %d 个，能量 %s → %s"
                       % (opened, energy, d.get("balance", "?"))}


def main():
    ap = argparse.ArgumentParser(description="WorkBuddy 每日积分（云端版）")
    ap.add_argument("--dry-run", action="store_true", help="只查询，不提交写请求")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--max-box", type=int, default=2, help="本次最多开几个盲盒")
    ap.add_argument("--no-travel", action="store_true", help="跳过猫猫旅行")
    ap.add_argument("--no-box", action="store_true", help="跳过盲盒")
    args = ap.parse_args()

    token = (os.environ.get("WB_TOKEN") or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        msg = ("缺少 WB_TOKEN。GitHub 里请把它加到 "
               "Settings -> Secrets and variables -> Actions")
        print(json.dumps({"error": msg}, ensure_ascii=False) if args.json else msg,
              file=sys.stderr)
        return 2

    domain = (os.environ.get("WB_DOMAIN") or DEFAULT_DOMAIN).strip().rstrip("/")
    if domain.startswith("http"):
        domain = domain.split("://", 1)[-1].strip("/")

    result = {"dry_run": args.dry_run, "domain": domain}
    errors = []

    try:
        result["checkin"] = do_checkin(domain, token, args.dry_run)
    except ApiError as exc:
        result["checkin"] = {"ok": False, "message": "签到失败：%s" % exc}
        errors.append(str(exc))

    if not args.no_travel:
        try:
            result["travel"] = do_travel(domain, token, args.dry_run)
        except ApiError as exc:
            result["travel"] = {"log": ["旅行失败：%s" % exc]}
            errors.append(str(exc))

    if not args.no_box:
        try:
            result["box"] = do_box(domain, token, args.dry_run, args.max_box)
        except ApiError as exc:
            result["box"] = {"message": "盲盒失败：%s" % exc}
            errors.append(str(exc))

    try:
        st, body = call(domain, token, PATHS["status"])
        d = data_of(st, body)
        result["summary"] = {
            "total_credits": d.get("total_credits"),
            "streak_days": d.get("streak_days"),
            "today_checked_in": d.get("today_checked_in"),
        }
    except ApiError:
        result["summary"] = {}

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if not errors else 1

    print("== WorkBuddy 每日积分%s ==" % ("（预览模式）" if args.dry_run else ""))
    ck = result.get("checkin") or {}
    print("1. 签到：%s" % ck.get("message", "未执行"))
    tv = result.get("travel") or {}
    print("2. 猫猫：%s" % " -> ".join(tv.get("log") or ["未执行"]))
    bx = result.get("box") or {}
    print("3. 盲盒：%s" % bx.get("message", "未执行"))
    s = result.get("summary") or {}
    if s:
        print("-" * 40)
        print("余额：%s | 连续：%s 天 | 今日已签：%s"
              % (s.get("total_credits"), s.get("streak_days"),
                 s.get("today_checked_in")))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
