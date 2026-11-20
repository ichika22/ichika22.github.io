#!/usr/bin/env python3
"""Publish only allowlisted Myfxbook gain, combined gain and source time."""
import datetime as dt
import decimal
import json
import os
import pathlib
import re
import sys
import urllib.parse
import urllib.request

API = "https://www.myfxbook.com/api/"
D = decimal.Decimal
# Historical periods, unchanged from the public pages. LIORA excludes the
# unauthorized trades and remains a reference figure, as documented there.
OLD = {"12290460": D("262.51"), "12290478": D("201.3"),
       "12290493": D("11.00"), "12290520": D("7.97")}
FALLBACK_DATES = {oid: dt.date(2026, 11, 2 if oid == "12290520" else 20) for oid in OLD}
FIELDS = {"gain", "combined", "sourceUpdated"}
MAX_BODY = 2 * 1024 * 1024
SOURCE_PATTERN = re.compile(r"[0-9]{2}/[0-9]{2}/[0-9]{4} [0-9]{2}:[0-9]{2}")
GAIN_PATTERN = re.compile(r"[+\-]?[0-9]{1,10}(?:\.[0-9]{1,10})?")


class ApiError(Exception):
    """Do not include URL, upstream bodies, credentials or private fields."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def api(method, **params):
    if method not in {"login", "get-my-accounts", "logout"}:
        raise ApiError
    # Myfxbook's HTTPS API documents login inputs in the query string.
    # Never print request URL, headers, response body or transport exceptions.
    url = API + method + ".json?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={
        "Accept": "application/json", "Cache-Control": "no-store",
        "User-Agent": "ESORA-Myfxbook-Combined/1.0",
    })
    try:
        with OPENER.open(request, timeout=20) as response:
            if response.status != 200:
                raise ApiError
            body = response.read(MAX_BODY + 1)
            if len(body) > MAX_BODY:
                raise ApiError
        payload = json.loads(body, parse_float=D)
        if not isinstance(payload, dict) or payload.get("error") is not False:
            raise ApiError
        return payload
    except (OSError, ValueError, TypeError, RecursionError):
        raise ApiError from None


def source_time(raw):
    if not isinstance(raw, str) or SOURCE_PATTERN.fullmatch(raw) is None:
        raise ValueError("source timestamp format")
    return dt.datetime.strptime(raw, "%m/%d/%Y %H:%M")


def valid_gain(raw):
    if type(raw) not in (str, D, int, float):
        raise ValueError("gain type")
    raw = str(raw)
    if not GAIN_PATTERN.fullmatch(raw):
        raise ValueError("gain format")
    gain = D(raw)
    if not D("-100") <= gain <= D("100000000"):
        raise ValueError("gain range")
    return gain




def compound(oid, gain):
    return (((1 + OLD[oid] / 100) * (1 + gain / 100) - 1) * 100).quantize(
        D("0.1"), rounding=decimal.ROUND_HALF_UP
    )


def previous_snapshot(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"), parse_float=D)
    accounts = data.get("accounts")
    if set(data) != {"version", "accounts"} or data["version"] != 1 or not isinstance(accounts, dict):
        raise ValueError("published snapshot format")
    for oid, record in accounts.items():
        if oid not in OLD or not isinstance(record, dict) or set(record) != FIELDS:
            raise ValueError("published snapshot fields")
        gain = valid_gain(record["gain"])
        if type(record["combined"]) not in (int, D) or record["combined"] != compound(oid, gain):
            raise ValueError("published snapshot calculation")
        if source_time(record["sourceUpdated"]).date() <= FALLBACK_DATES[oid]:
            raise ValueError("published snapshot date")
    return accounts


def updates(api_accounts, previous, today):
    if not isinstance(api_accounts, list):
        raise ValueError("invalid account list")
    by_oid = {oid: [] for oid in OLD}
    for raw in api_accounts:
        if not isinstance(raw, dict):
            continue
        raw_oid = raw.get("id")
        if type(raw_oid) not in (str, int):
            continue
        oid = str(raw_oid)
        if oid in by_oid:
            by_oid[oid].append(raw)
    output, changed, eligible = dict(previous), 0, 0
    for oid, candidates in by_oid.items():
        if len(candidates) != 1:
            continue
        source = candidates[0].get("lastUpdateDate")
        try:
            timestamp = source_time(source)
            gain = valid_gain(candidates[0].get("gain"))
            if timestamp.date() > today + dt.timedelta(days=1):
                continue
            eligible += 1
            if timestamp.date() <= FALLBACK_DATES[oid]:
                continue
            if oid in previous and timestamp <= source_time(previous[oid]["sourceUpdated"]):
                continue
            output[oid] = {"gain": gain, "combined": compound(oid, gain), "sourceUpdated": source}
            changed += 1
        except (ValueError, decimal.DecimalException):
            continue
    return output, changed, eligible


def encode(data):
    # Exact decimal formatting preserves provider gain without floats
    # changing the last decimal. The browser verifies the schema before use.
    # The prior file is read as JSON numbers; emit decimal JSON numbers exactly.
    out = ['{"version":1,"accounts":{']
    for oid, r in sorted(data.items()):
        if len(out) > 1:
            out.append(",")
        out.append(json.dumps(oid) + ':{"combined":' + format(D(r["combined"]), "f")
                   + ',"gain":' + format(D(r["gain"]), "f")
                   + ',"sourceUpdated":' + json.dumps(r["sourceUpdated"]) + "}")
    out.append("}}\n")
    return "".join(out)


def main(path):
    email = os.environ.get("MYFXBOOK_EMAIL")
    password = os.environ.get("MYFXBOOK_PASSWORD")
    if not email or not password:
        print("Myfxbook connection not configured; no figures changed.")
        return 0
    try:
        previous = previous_snapshot(path)
    except (OSError, TypeError, ValueError, AttributeError, KeyError, decimal.DecimalException):
        print("Published figures failed validation; no figures changed.", file=sys.stderr)
        return 1
    session = None
    try:
        session = api("login", email=email, password=password).get("session")
        if not isinstance(session, str) or not 1 <= len(session) <= 128:
            raise ApiError
        snapshot, changed, eligible = updates(
            api("get-my-accounts", session=session).get("accounts"), previous,
            dt.datetime.now(dt.timezone.utc).date(),
        )
        if not eligible:
            print("No eligible Myfxbook accounts returned; no figures changed.", file=sys.stderr)
            return 1
        if changed:
            path.write_text(encode(snapshot), encoding="utf-8")
            print(f"Validated new Myfxbook figures for {changed} account(s).")
        else:
            print("No newer Myfxbook figures; no figures changed.")
        return 0
    except (ApiError, OSError, ValueError, TypeError, decimal.DecimalException):
        print("Myfxbook refresh could not complete; no publication.", file=sys.stderr)
        return 1
    finally:
        if isinstance(session, str) and 1 <= len(session) <= 128:
            try:
                api("logout", session=session)
            except ApiError:
                print("Myfxbook session logout not confirmed.", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: refresh_myfxbook_combined.py OUTPUT_JSON")
    sys.exit(main(pathlib.Path(sys.argv[1])))
