"""
微信公众号草稿箱工具

  python frontends/wxoaapp.py token
  python frontends/wxoaapp.py upload_thumb /path/to/cover.jpg
  python frontends/wxoaapp.py add_draft --title "标题" --content "HTML" [--author ...] [--digest ...] [--thumb ...]
  python frontends/wxoaapp.py add_draft --title "标题" --content @/path/to/file.html

mykey.py: wx_oa_appid, wx_oa_appsecret
"""

import json, os, sys, time, argparse
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llmcore import mykeys

API_BASE = "https://api.weixin.qq.com/cgi-bin"


# ── API 客户端 ────────────────────────────────

class WxOAClient:
    """封装微信公众号 API，支持外部注入 appid/secret 以便测试和复用。"""

    def __init__(self, appid=None, secret=None):
        self.appid = appid or (mykeys.get("wx_oa_appid") or "").strip()
        self.secret = secret or (mykeys.get("wx_oa_appsecret") or "").strip()
        self._token = ""
        self._token_expires_at = 0

    def _ensure_config(self):
        if not self.appid or not self.secret:
            raise RuntimeError("请在 mykey.py 中配置 wx_oa_appid 和 wx_oa_appsecret")

    def get_access_token(self):
        self._ensure_config()
        if time.time() < self._token_expires_at - 60:
            return self._token
        r = requests.get(
            f"{API_BASE}/token",
            params={"grant_type": "client_credential", "appid": self.appid, "secret": self.secret},
            timeout=10,
        ).json()
        if "access_token" not in r:
            raise RuntimeError(f"获取 access_token 失败: {r}{_whitelist_hint(r)}")
        self._token = r["access_token"]
        self._token_expires_at = time.time() + r.get("expires_in", 7200)
        return self._token

    def upload_thumb(self, image_path):
        token = self.get_access_token()
        with open(image_path, "rb") as f:
            r = requests.post(
                f"{API_BASE}/material/add_material",
                params={"access_token": token, "type": "image"},
                files={"media": (os.path.basename(image_path), f)},
                timeout=30,
            ).json()
        if "media_id" not in r:
            raise RuntimeError(f"上传封面图失败: {r}{_whitelist_hint(r)}")
        return r["media_id"]

    def add_draft(self, articles):
        token = self.get_access_token()
        payload = json.dumps({"articles": articles}, ensure_ascii=False).encode("utf-8")
        r = requests.post(
            f"{API_BASE}/draft/add",
            params={"access_token": token},
            data=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        ).json()
        if "media_id" not in r:
            raise RuntimeError(f"上传草稿失败: {r}{_whitelist_hint(r)}")
        return r["media_id"]


# ── 工具函数 ────────────────────────────────

_WHITELIST_KEYWORDS = ("40164", "whitelist", "白名单", "not in whitelist")

def _whitelist_hint(resp) -> str:
    s = json.dumps(resp, ensure_ascii=False) if isinstance(resp, dict) else str(resp)
    low = s.lower()
    if not any(kw in low for kw in _WHITELIST_KEYWORDS):
        return ""
    return (
        "\n[提示] 当前出口 IP 未在公众号「IP 白名单」内。"
        "请查看上方微信返回的 errmsg（一般会写出被拒绝的 IP），"
        "到微信公众平台 → 设置与开发 → 基本配置 → IP白名单，将该 IP 加入后重试。"
    )


def load_content(content: str) -> str:
    """若以 @ 开头则读取该文件 UTF-8 全文，否则原样返回。"""
    head = str(content).strip()
    if not head.startswith("@"):
        return content
    path_part = head[1:].strip()
    if not path_part:
        raise ValueError("--content 以 @ 开头但路径为空")
    path = os.path.abspath(os.path.expanduser(path_part))
    if not os.path.isfile(path):
        raise FileNotFoundError(f"文件不存在或不是普通文件: {path_part!r} -> {path!r}")
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


# ── CLI ────────────────────────────────

def _build_parser():
    parser = argparse.ArgumentParser(description="微信公众号草稿箱工具")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("token", help="获取并打印 access_token")
    p_thumb = sub.add_parser("upload_thumb", help="上传封面图")
    p_thumb.add_argument("image", help="图片路径")
    p_draft = sub.add_parser("add_draft", help="上传文章到草稿箱")
    p_draft.add_argument("--title", required=True)
    p_draft.add_argument("--content", required=True, help="HTML 正文；若以 @ 开头则为文件路径（UTF-8）")
    p_draft.add_argument("--author", default="")
    p_draft.add_argument("--digest", default="")
    p_draft.add_argument("--thumb", default="", help="封面图路径（可选）")
    p_draft.add_argument("--thumb_media_id", default="", help="已有封面 media_id（可选）")
    return parser


def _run_add_draft(client, args):
    content = load_content(args.content)
    thumb_media_id = args.thumb_media_id
    if args.thumb and not thumb_media_id:
        thumb_media_id = client.upload_thumb(args.thumb)
        print(f"封面已上传: {thumb_media_id}")
    article = {"title": args.title, "content": content, "author": args.author, "digest": args.digest}
    if thumb_media_id:
        article["thumb_media_id"] = thumb_media_id
    media_id = client.add_draft([article])
    print(f"草稿已上传，media_id: {media_id}")


def main():
    parser = _build_parser()
    args = parser.parse_args()
    client = WxOAClient()

    try:
        if args.cmd == "token":
            print(client.get_access_token())
        elif args.cmd == "upload_thumb":
            print(f"thumb_media_id: {client.upload_thumb(args.image)}")
        elif args.cmd == "add_draft":
            _run_add_draft(client, args)
        else:
            parser.print_help()
    except (RuntimeError, OSError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
