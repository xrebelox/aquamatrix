from __future__ import annotations
import re, json
from typing import Any, Dict, Optional, List, Tuple
from urllib.parse import urljoin
from aiohttp import ClientSession
class SMSNetClient:
    def __init__(self, session: ClientSession, base_url: str, tenant: str, username: str, password: str, logger) -> None:
        self._session = session
        self._base = base_url.rstrip("/")
        self._tenant = tenant.strip("/")
        self._username = username
        self._password = password
        self._logger = logger
        self._rvt: Optional[str] = None
    def _url(self, path: str) -> str:
        return f"{self._base}/{self._tenant}/{path.lstrip('/')}"
    async def _fetch(self, method: str, url: str, **kwargs):
        self._logger.debug("SMSNET %s %s", method, url)
        async with self._session.request(method, url, **kwargs) as resp:
            text = await resp.text()
            self._logger.debug("SMSNET %s %s -> %s head=%s", method, url, resp.status, text[:250])
            return resp, text
    async def _get_login_page(self) -> Tuple[str, str]:
        login_url = self._url("Account/Login")
        headers = {"User-Agent": "HomeAssistant", "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8"}
        resp, text = await self._fetch("GET", login_url, headers=headers)
        if resp.status >= 400:
            raise Exception(f"Login GET failed: {resp.status}")
        return login_url, text
    def _parse_login_form(self, base_url: str, html: str) -> Tuple[str, Dict[str, str], str, str]:
        form_re = re.compile(r'<form[^>]*method=["\\\']?post["\\\']?[^>]*>(.*?)</form>', re.I | re.S)
        mform = form_re.search(html)
        if not mform: raise Exception("Login form not found")
        form_html = mform.group(0)
        action_m = re.search(r'action=["\\\']([^"\\\']*)["\\\']', form_html, re.I)
        action = action_m.group(1) if action_m else ""
        action_url = urljoin(base_url, action) if action else base_url
        inputs = re.findall(r'<input[^>]*>', form_html, re.I)
        data: Dict[str, str] = {}
        username_candidates: List[str] = []
        password_name: Optional[str] = None
        for inp in inputs:
            name_m = re.search(r'name=["\\\']([^"\\\']+)["\\\']', inp, re.I)
            if not name_m: continue
            name = name_m.group(1)
            type_m = re.search(r'type=["\\\']([^"\\\']+)["\\\']', inp, re.I)
            itype = (type_m.group(1).lower() if type_m else "text")
            val_m = re.search(r'value=["\\\']([^"\\\']*)["\\\']', inp, re.I)
            value = val_m.group(1) if val_m else ""
            if "__RequestVerificationToken" in name:
                data[name] = value; continue
            if itype == "password":
                password_name = name; continue
            if itype == "hidden":
                data[name] = value; continue
            username_candidates.append(name)
        user_field = username_candidates[0] if username_candidates else "Email"
        if password_name is None: password_name = "Password"
        data[user_field] = self._username
        data[password_name] = self._password
        if "RememberMe" in (n for n in data.keys()) or "RememberMe" in html:
            data["RememberMe"] = "true"
        self._logger.debug("SMSNET login form: action=%s user_field=%s pass_field=%s", action_url, user_field, password_name)
        return action_url, data, user_field, password_name
    async def login_basic(self) -> None:
        login_url, html = await self._get_login_page()
        action_url, data, _, _ = self._parse_login_form(login_url, html)
        headers = {"Content-Type": "application/x-www-form-urlencoded", "Origin": self._base, "Referer": login_url, "User-Agent": "HomeAssistant"}
        resp, text = await self._fetch("POST", action_url, data=data, headers=headers, allow_redirects=True)
        if resp.status >= 400: raise Exception(f"Login POST failed: {resp.status}")
        await self._refresh_page_token()
    async def login(self) -> None:
        login_url, html = await self._get_login_page()
        action_url, data, _, _ = self._parse_login_form(login_url, html)
        headers = {"Content-Type": "application/x-www-form-urlencoded", "Origin": self._base, "Referer": login_url, "User-Agent": "HomeAssistant"}
        resp, text = await self._fetch("POST", action_url, data=data, headers=headers, allow_redirects=True)
        if resp.status >= 400: raise Exception(f"Login POST failed: {resp.status}")
        await self._refresh_page_token()
        try:
            await self._get_json_once("ReadingsAndConsumptions/GetLastReadingInfo", "ReadingsAndConsumptions", pair_tokens=False)
        except Exception:
            await self._refresh_page_token()
            await self._get_json_once("ReadingsAndConsumptions/GetLastReadingInfo", "ReadingsAndConsumptions", pair_tokens=True)
    def _extract_cookie_token(self) -> Optional[str]:
        jar = self._session.cookie_jar
        for cookie in jar:
            if cookie.key.startswith("__RequestVerificationToken"):
                return cookie.value
        return None
    async def _refresh_page_token(self) -> str:
        url = self._url("ReadingsAndConsumptions")
        resp, text = await self._fetch("GET", url, headers={"User-Agent": "HomeAssistant"})
        m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', text, re.I)
        if m: self._rvt = m.group(1)
        return self._rvt or ""
    def _ajax_headers(self, referer_path: str, pair_tokens: bool = False) -> Dict[str, str]:
        ref = self._url(referer_path); rvt = self._rvt or ""
        headers = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json, text/plain, */*", "Referer": ref, "User-Agent": "HomeAssistant"}
        if rvt:
            if pair_tokens:
                cookie_tok = self._extract_cookie_token() or ""
                value = f"{rvt}:{cookie_tok}" if cookie_tok else rvt
                headers["RequestVerificationToken"] = value
                headers["X-RequestVerificationToken"] = value
            else:
                headers["RequestVerificationToken"] = rvt
                headers["X-RequestVerificationToken"] = rvt
        return headers
    async def _get_json_once(self, path: str, referer_path: str, pair_tokens: bool) -> Any:
        url = self._url(path); headers = self._ajax_headers(referer_path, pair_tokens=pair_tokens)
        self._logger.debug("SMSNET GET %s (pair=%s)", url, pair_tokens)
        async with self._session.get(url, headers=headers) as resp:
            text = await resp.text()
            self._logger.debug("SMSNET GET %s status=%s head=%s", path, resp.status, text[:200])
            if resp.status != 200: raise Exception(f"GET {path} failed: {resp.status}; head={text[:200]}")
            try: return await resp.json(content_type=None)
            except Exception: return json.loads(text)
    async def _get_json(self, path: str, referer_path: str) -> Any:
        try: return await self._get_json_once(path, referer_path, pair_tokens=False)
        except Exception as e1:
            self._logger.debug("SMSNET first GET failed: %s", e1)
            await self._refresh_page_token()
            try: return await self._get_json_once(path, referer_path, pair_tokens=True)
            except Exception:
                await self.login()
                return await self._get_json_once(path, referer_path, pair_tokens=True)
    async def _try_paths(self, paths: List[str], referer_path: str) -> Any:
        last_exc: Optional[Exception] = None
        for p in paths:
            try: return await self._get_json(p, referer_path)
            except Exception as e: last_exc = e; self._logger.debug("SMSNET path failed %s -> %s", p, e)
        raise last_exc or Exception("All paths failed")
    async def get_last_reading(self) -> Any:
        return await self._try_paths(["ReadingsAndConsumptions/GetLastReadingInfo", "Readings/GetLastReadingInfo"], "ReadingsAndConsumptions")
    async def get_consumptions_graph(self) -> Any:
        return await self._try_paths(["ReadingsAndConsumptions/GetConsumptionsGraph", "Readings/GetConsumptionsGraph"], "ReadingsAndConsumptions")
    async def get_billed_graph(self) -> Any:
        return await self._get_json("Billing/GetBilledValuesGraph", "Home/Index")
    async def get_billing_info(self) -> Any:
        return await self._get_json("Billing/GetBillingInfo", "Home/Index")
