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

APPID = str(mykeys.get("wx_oa_appid", "") or "").strip()
SECRET = str(mykeys.get("wx_oa_appsecret", "") or "").strip()
API = "https://api.weixin.qq.com/cgi-bin"
_TOKEN_CACHE = {"token": "", "expires_at": 0}


def _whitelist_ip_reminder(resp) -> str:
    s = json.dumps(resp, ensure_ascii=False) if isinstance(resp, dict) else str(resp)
    if "40164" not in s and "whitelist" not in s.lower() and "白名单" not in s and "not in whitelist" not in s.lower():
        return ""
    return (
        "\n[提示] 当前出口 IP 未在公众号「IP 白名单」内。"
        "请查看上方微信返回的 errmsg（一般会写出被拒绝的 IP），"
        "到微信公众平台 → 设置与开发 → 基本配置 → IP白名单，将该 IP 加入后重试。"
    )


def get_access_token():
    if time.time() < _TOKEN_CACHE["expires_at"] - 60:
        return _TOKEN_CACHE["token"]
    r = requests.get(
        f"{API}/token",
        params={"grant_type": "client_credential", "appid": APPID, "secret": SECRET},
        timeout=10,
    ).json()
    if "access_token" not in r:
        raise RuntimeError(f"获取 access_token 失败: {r}{_whitelist_ip_reminder(r)}")
    _TOKEN_CACHE["token"] = r["access_token"]
    _TOKEN_CACHE["expires_at"] = time.time() + r.get("expires_in", 7200)
    return _TOKEN_CACHE["token"]


def upload_thumb(image_path):
    token = get_access_token()
    with open(image_path, "rb") as f:
        r = requests.post(
            f"{API}/material/add_material",
            params={"access_token": token, "type": "image"},
            files={"media": (os.path.basename(image_path), f)},
            timeout=30,
        ).json()
    if "media_id" not in r:
        raise RuntimeError(f"上传封面图失败: {r}{_whitelist_ip_reminder(r)}")
    return r["media_id"]


def add_draft(articles):
    token = get_access_token()
    payload = json.dumps({"articles": articles}, ensure_ascii=False).encode("utf-8")
    r = requests.post(
        f"{API}/draft/add",
        params={"access_token": token},
        data=payload,
        headers={"Content-Type": "application/json"},
        timeout=30,
    ).json()
    if "media_id" not in r:
        raise RuntimeError(f"上传草稿失败: {r}{_whitelist_ip_reminder(r)}")
    return r["media_id"]


def _check_config():
    if not APPID or not SECRET:
        print("ERROR: 请在 mykey.py 中配置 wx_oa_appid 和 wx_oa_appsecret")
        sys.exit(1)


def load_content_from_arg(content: str) -> str:
    """--content 若以 @ 开头则读取该文件 UTF-8 全文；否则原样作为正文。"""
    if not isinstance(content, str):
        content = str(content)
    head = content.strip()
    if not head.startswith("@"):
        return content
    path_part = head[1:].strip()
    if not path_part:
        raise ValueError("--content 以 @ 开头但路径为空")
    path = os.path.expanduser(path_part)
    if not os.path.isabs(path):
        path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"文件不存在或不是普通文件: {path_part!r} -> {path!r}"
        )
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def main():
    parser = argparse.ArgumentParser(description="微信公众号草稿箱工具")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("token", help="获取并打印 access_token")

    p_thumb = sub.add_parser("upload_thumb", help="上传封面图")
    p_thumb.add_argument("image", help="图片路径")

    p_draft = sub.add_parser("add_draft", help="上传文章到草稿箱")
    p_draft.add_argument("--title", required=True)
    p_draft.add_argument(
        "--content",
        required=True,
        help="HTML 正文；若以 @ 开头则为文件路径（UTF-8）",
    )
    p_draft.add_argument("--author", default="")
    p_draft.add_argument("--digest", default="")
    p_draft.add_argument("--thumb", default="", help="封面图路径（可选）")
    p_draft.add_argument("--thumb_media_id", default="", help="已有封面 media_id（可选）")

    args = parser.parse_args()
    _check_config()

    try:
        if args.cmd == "token":
            print(get_access_token())
        elif args.cmd == "upload_thumb":
            mid = upload_thumb(args.image)
            print(f"thumb_media_id: {mid}")
        elif args.cmd == "add_draft":
            try:
                content = load_content_from_arg(args.content)
            except (OSError, ValueError) as e:
                print(f"ERROR: {e}", file=sys.stderr)
                sys.exit(2)
            thumb_media_id = args.thumb_media_id
            if args.thumb and not thumb_media_id:
                thumb_media_id = upload_thumb(args.thumb)
                print(f"封面已上传: {thumb_media_id}")
            article = {
                "title": args.title,
                "content": content,
                "author": args.author,
                "digest": args.digest,
            }
            if thumb_media_id:
                article["thumb_media_id"] = thumb_media_id
            media_id = add_draft([article])
            print(f"草稿已上传，media_id: {media_id}")
        else:
            parser.print_help()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
