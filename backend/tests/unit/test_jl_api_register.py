"""直连注册 API 引擎(in1.fun / rztk6mpvx / 7aamx 同族白标)的纯函数回归。

重点覆盖 7aamx(墨西哥)接入引入的分地区行为:号码本地化、语料选择、以及生成的
账号密码必须满足站点 /wps/system/setting/register 声明的校验
(username 6-13 / password 6-12,均 ^[a-zA-Z0-9]+$)——不合规会被服务端直接拒。
同时锁住存量孟加拉站(bd)的行为不被改动带偏。
"""
import re

import pytest

from app.workers import jl_api_register as jl


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+5215512345678", "5512345678"),   # 旧式 52 1 + 10 位
        ("5215512345678", "5512345678"),
        ("+525512345678", "5512345678"),    # 现行 52 + 10 位
        ("+52 1 55 1234 5678", "5512345678"),
        ("00525512345678", "5512345678"),   # 国际接入码 00
        ("5512345678", "5512345678"),       # 已是本地号
        ("+528616190623", "8616190623"),
        ("+8801712345678", None),           # 孟加拉号不是合法 MX 号
        ("12345", None),
        ("", None),
    ],
)
def test_to_mx_mobile(raw, expected):
    assert jl.to_mx_mobile(raw) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+8801712345678", "01712345678"),
        ("8801712345678", "01712345678"),
        ("01712345678", "01712345678"),
        ("+5215512345678", None),
    ],
)
def test_to_bd_mobile_unchanged(raw, expected):
    """存量孟加拉站行为不得被 MX 接入改动。"""
    assert jl.to_bd_mobile(raw) == expected


@pytest.mark.unit
def test_to_local_mobile_dispatch():
    assert jl.to_local_mobile("+5215512345678", "mx") == "5512345678"
    assert jl.to_local_mobile("+8801712345678", "bd") == "01712345678"
    # 未知地区回落 bd 规则(存量默认)
    assert jl.to_local_mobile("+8801712345678", "zz") == "01712345678"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("host", "merchant"),
    [
        ("www.7aamx.cc", "7aamxns1"),
        ("7aamx.cc", "7aamxns1"),
        ("7aadx16.7aamx.cc", "7aamxns1"),   # 推广码子域轮换
        ("www.rztk6mpvx.com", "8kbdtf4"),
        ("in1.fun", "jilievof2"),
        ("7aamx.cc.evil.com", None),        # 后缀匹配不能被仿冒域骗过
        ("example.com", None),
        ("", None),
    ],
)
def test_merchant_for_host(host, merchant):
    assert jl.merchant_for_host(host) == merchant


@pytest.mark.unit
@pytest.mark.parametrize(
    ("host", "country", "locale"),
    [
        ("www.7aamx.cc", "", "mx"),
        ("7aadx16.7aamx.cc", "", "mx"),
        ("in1.fun", "", "bd"),
        ("www.rztk6mpvx.com", "", "bd"),
        ("unknown.com", "MX", "mx"),        # 域名未登记时按短信国家判定
        ("unknown.com", "", "bd"),          # 都取不到 → 存量默认
    ],
)
def test_locale_for(host, country, locale):
    assert jl.locale_for(host, country) == locale


@pytest.mark.unit
def test_locale_for_config_overrides_domain():
    """后台脚本 name_locale 优先级最高(站点换地区无需改代码)。"""
    assert jl.locale_for("in1.fun", "BD", {"name_locale": "mx"}) == "mx"


@pytest.mark.unit
@pytest.mark.parametrize("locale", ["mx", "bd"])
def test_generated_identity_matches_site_rules(locale):
    """账号 6-13 位、密码 6-12 位,且都只含字母数字(站点正则 ^[a-zA-Z0-9]+$)。"""
    for _ in range(500):
        assert re.fullmatch(r"[a-zA-Z0-9]{6,13}", jl._gen_username(locale))
        assert re.fullmatch(r"[a-zA-Z0-9]{6,12}", jl._gen_password(locale))


@pytest.mark.unit
def test_generated_username_varies():
    """同地区批量生成需足够分散,避免整批注册撞名后被查重挡下。"""
    names = {jl._gen_username("mx") for _ in range(500)}
    assert len(names) > 300


@pytest.mark.unit
def test_mx_corpus_is_spanish():
    """MX 站不能用孟加拉名库(一眼假)。"""
    names, words, _ = jl._corpus("mx")
    assert "carlos" in names and "rakib" not in names
    assert "azteca" in words
    assert jl._corpus("bd")[0] is jl._NAMES


@pytest.mark.unit
@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("https://www.7aamx.cc/?tid=5605&affiliateCode=7aadx16", "7aadx16"),
        ("https://7aadx16.7aamx.cc/", "7aadx16"),          # 推广码在子域
        ("https://www.7aamx.cc/m/register?tid=5605", ""),  # 没带码
        ("https://www.7aamx.cc/?tid=5711&affiliateCode=7aadx37", "7aadx37"),
    ],
)
def test_extract_affiliate(url, code):
    assert jl.extract_affiliate(url) == code


@pytest.mark.unit
def test_extract_affiliate_ignores_short_link_channel_param():
    """中间营销页的 ?ch=xxx 是短链渠道追踪码,不是 affiliateCode,误当推广码会把归属写错。"""
    assert jl.extract_affiliate("https://www.7aa69.vip/?ch=1f2bbbcb94") == ""


@pytest.mark.unit
def test_landing_campaign_carries_affiliate_when_url_has_none():
    """短链落到中间页时,URL 上没有 affiliateCode,只能靠页面配置的 agentName 兜住归属。"""
    html = ('{"merchantCode":"7aamxns1","domainName":"www.7aa69.vip","agentName":"7aadx37",'
            '"redirectDomains":["https://www.7aamx.me","https://www.7aamx.cc"]}')
    merchant, affiliate, bases = jl.parse_landing_campaign(html)
    assert (merchant, affiliate) == ("7aamxns1", "7aadx37")
    assert jl.extract_affiliate("https://www.7aa69.vip/?ch=1f2bbbcb94") == ""  # URL 侧取不到
    assert bases


@pytest.mark.unit
def test_parse_landing_campaign():
    """短链落到中间营销页时,要能从页面配置读出真站马甲域池 + 商户号 + 推广码。"""
    html = (
        '<html><body><script>window.__CFG__={"id":1,"status":1,'
        '"merchantCode":"7aamxns1","domainName":"www.7aa88.vip","agentName":"7aadx16",'
        '"redirectDomains":["https://www.7aamx.xyz","https://www.7aamx.me",'
        '"https://www.7aamx.cc/","https://www.7aamx.shop","https://www.7aamx.vip"]}'
        '</script></body></html>'
    )
    merchant, affiliate, bases = jl.parse_landing_campaign(html)
    assert merchant == "7aamxns1"
    assert affiliate == "7aadx16"
    assert bases[0] == "https://www.7aamx.xyz"
    assert "https://www.7aamx.cc" in bases      # 尾部斜杠要归一,否则拼出 //wps 路径
    assert len(bases) == 5
    # 每个真站域都必须能解析回商户号,否则会错落 DEFAULT_MERCHANT 建到别家站
    from urllib.parse import urlparse
    for b in bases:
        assert jl.merchant_for_host(urlparse(b).hostname) == "7aamxns1"


@pytest.mark.unit
def test_parse_landing_campaign_on_non_landing_page():
    """真站 SPA 骨架没有 redirectDomains → 返回空,调用方据此判定不需要切域。"""
    assert jl.parse_landing_campaign("<html><body><div id=app></div></body></html>") == (None, "", [])
    assert jl.parse_landing_campaign("") == (None, "", [])


@pytest.mark.unit
def test_looks_like_white_label_真站骨架():
    """真站首页靠 aboutMerchant.js + encrypt.js 这对固定构建指纹识别。"""
    html = ('<head><script src="/js/aboutMerchant.js?v=28379"></script>'
            '<script src="/js/encrypt.js?v=28379"></script></head><body><div id=app></div></body>')
    assert jl.looks_like_white_label(html) is True


@pytest.mark.unit
def test_looks_like_white_label_中间营销页():
    """新活动的中间页域(7aaNN.vip)不在白名单里,只能靠 merchantCode+redirectDomains 识别。"""
    html = ('{"merchantCode":"7aamxns1","agentName":"7aadx37",'
            '"redirectDomains":["https://www.7aamx.me","https://www.7aamx.cc"]}')
    assert jl.looks_like_white_label(html) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "html",
    [
        "",
        "<html><body>某个无关落地页</body></html>",
        '{"merchantCode":"7aamxns1"}',                        # 只有商户号,没有真站域池
        '{"redirectDomains":["https://www.other.com"]}',      # 只有域池,没有商户号
        '<script src="/js/encrypt.js"></script>',             # 只命中半个构建指纹
    ],
)
def test_looks_like_white_label_不误判(html):
    """误判会把别家站(TK688/1win 等)拖进直连 API 路径,必然失败,故宁可漏判不可错判。"""
    assert jl.looks_like_white_label(html) is False


@pytest.mark.unit
def test_phone_to_username_localized():
    """撞库用户名按地区取本地号(MX 10 位 / BD 11 位),并满足 6-13 位限制。"""
    assert jl.phone_to_username("+528616190623", "mx") == "8616190623"
    assert jl.phone_to_username("+8801712345678", "bd") == "01712345678"
