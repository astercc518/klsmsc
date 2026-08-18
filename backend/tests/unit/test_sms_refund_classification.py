"""退款资格分类：区分「上游拒收未发出」与「已提交到上游」。

回归自 ch82 TS 泰国直连事故：模板拒收(SMPP status=1)的 29 万条曾被当成"已提交"，
全部进不了管理员可退候选。SMPP 协议规定 submit_sm_resp 的 command_status 非零时
应答不含 message_id——消息从未进入上游系统，属于未发出。
"""
from types import SimpleNamespace

from app.services.sms_refund import (
    _looks_submitted_to_upstream,
    classify_refund_candidate,
    is_content_rejected,
)


def _log(err, umid=None, status="failed", cost="0.005", refunded=None):
    return SimpleNamespace(
        status=status, refunded_at=refunded, cost_price=cost,
        error_message=err, upstream_message_id=umid,
    )


def test_upstream_reject_is_refund_eligible():
    # submit_sm_resp 非零 = 上游拒收、从未投递 → 该进管理员可退候选
    for err in ("SMPP Error: 1", "SMPP Error: 88 (throttled, retries exhausted)", "SMPP Error: 69"):
        r = classify_refund_candidate(_log(err))
        assert r.eligible is True, err
        assert "上游拒收未发出" in r.reason


def test_known_reject_codes_are_explained_for_admin():
    assert "模板未报备" in classify_refund_candidate(_log("SMPP Error: 1")).reason
    assert "限流" in classify_refund_candidate(_log("SMPP Error: 88")).reason


def test_retried_batch_is_flagged_against_double_compensation():
    r = classify_refund_candidate(_log("SMPP Error: 1 [已转批次 #1526 重发]"))
    assert r.eligible is True
    assert "勿重复补偿" in r.reason


def test_delivered_or_unknown_outcome_stays_ineligible():
    for err in ("SMPP DLR: stat=UNDELIV err=000", "DLR 超时: 超过72小时未收到终态回执"):
        assert classify_refund_candidate(_log(err)).eligible is False
    # 拿到上游 message_id 是"已提交"的硬证据，压过 error_message
    assert classify_refund_candidate(_log("SMPP Error: 1", umid="abc123")).eligible is False


def test_non_smpp_system_errors_unaffected():
    assert classify_refund_candidate(_log("No available channel")).eligible is True
    assert classify_refund_candidate(_log("SMPP Error: 1", refunded="2026-08-18")).eligible is False


def test_content_reject_is_refundable_but_not_retryable():
    """两个判断必须分开：拒收=该退，但原样重发必然再拒(ch108 教训)。"""
    template_reject = _log("SMPP Error: 1")
    assert classify_refund_candidate(template_reject).eligible is True   # 可退
    assert is_content_rejected(template_reject) is True                  # 不可原样重发
    assert _looks_submitted_to_upstream(template_reject) is False

    # 限流是临时问题：可退，也可以重发
    throttled = _log("SMPP Error: 88 (throttled, retries exhausted)")
    assert classify_refund_candidate(throttled).eligible is True
    assert is_content_rejected(throttled) is False

    # 非 SMPP 拒收的系统错误不受影响
    assert is_content_rejected(_log("No available channel")) is False
