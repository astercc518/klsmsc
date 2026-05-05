"""
PicklePersistence + Fernet 对称加密。

旧实现：bot_data.pickle 明文，含全部用户对话状态、半填充注册信息、绑定 token 等。
容器内任何能读 bot 工作目录的进程或 host root 都能直接 pickle.load。

策略：
  - 整个 pickle bytes 用 Fernet (AES-128 + HMAC) 加密后再写盘
  - PTB 内部用 _BotPickler / _BotUnpickler 处理 bot 引用占位符，
    所以加密层包在 _BotPickler 输出之外（先 pickle 序列化，再加密；反之）
  - 旧明文文件启动时一次性迁移到密文
"""
import io
import os
import pickle
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from telegram.ext import PicklePersistence
from telegram.ext._utils.types import BD, CD, UD


# Fernet token 以 base64 字符开头（"gAAAA..."），明文 pickle 多以 \x80 开头
_PLAIN_PICKLE_PREFIXES = (b"\x80", b"\x00")


def _is_plaintext_pickle(data: bytes) -> bool:
    return bool(data) and data[:1] in _PLAIN_PICKLE_PREFIXES


class EncryptedPicklePersistence(PicklePersistence):
    """
    覆盖 _load_singlefile / _dump_singlefile 加上 Fernet 层。
    PTB 默认 single_file=True，所有数据存一个文件，对应这两个方法。
    多文件模式需要另外覆盖 _load_file / _dump_file。
    """

    def __init__(self, filepath: str, fernet_key: bytes, **kwargs):
        if not fernet_key:
            raise RuntimeError(
                "BOT_PERSISTENCE_KEY 必须配置：python -c "
                "\"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        self._fernet = Fernet(fernet_key)
        super().__init__(filepath=filepath, **kwargs)

    # ---- single_file 模式 ----
    def _load_singlefile(self) -> None:
        """读取整个 single 文件；明文 → 解 pickle.load；密文 → 解密 → pickle.load。
        无论哪种结果，下一次 _dump 都会写密文（实现一次性迁移）。"""
        from telegram.ext._picklepersistence import _BotUnpickler

        try:
            with self.filepath.open("rb") as f:
                raw = f.read()
        except OSError:
            # 文件不存在/无权读：等同首次启动
            self.conversations = {}
            self.user_data = {}
            self.chat_data = {}
            self.bot_data = self.context_types.bot_data()
            self.callback_data = None
            return

        if not raw:
            self.conversations = {}
            self.user_data = {}
            self.chat_data = {}
            self.bot_data = self.context_types.bot_data()
            self.callback_data = None
            return

        # 选择解密路径
        if _is_plaintext_pickle(raw):
            buf = io.BytesIO(raw)
        else:
            try:
                buf = io.BytesIO(self._fernet.decrypt(raw))
            except InvalidToken:
                # key 不匹配 → 视为坏文件，重新初始化
                self.conversations = {}
                self.user_data = {}
                self.chat_data = {}
                self.bot_data = self.context_types.bot_data()
                self.callback_data = None
                return

        try:
            data = _BotUnpickler(self.bot, buf).load()
        except (pickle.UnpicklingError, Exception) as exc:
            raise TypeError(
                f"加密 pickle 解包失败 {self.filepath.name}: {exc}"
            ) from exc

        self.user_data = data["user_data"]
        self.chat_data = data["chat_data"]
        self.bot_data = data.get("bot_data", self.context_types.bot_data())
        self.callback_data = data.get("callback_data", {})
        self.conversations = data["conversations"]

    def _dump_singlefile(self) -> None:
        """落盘前先 _BotPickler 序列化为 bytes，再 Fernet 加密；原子写。"""
        from telegram.ext._picklepersistence import _BotPickler

        data = {
            "conversations": self.conversations,
            "user_data": self.user_data,
            "chat_data": self.chat_data,
            "bot_data": self.bot_data,
            "callback_data": self.callback_data,
        }
        buf = io.BytesIO()
        _BotPickler(self.bot, buf, protocol=pickle.HIGHEST_PROTOCOL).dump(data)
        encrypted = self._fernet.encrypt(buf.getvalue())

        tmp_path = Path(f"{self.filepath}.tmp")
        with tmp_path.open("wb") as f:
            f.write(encrypted)
        os.replace(str(tmp_path), str(self.filepath))

    # ---- 多文件模式（保险起见也覆盖一份）----
    def _load_file(self, filepath: Path):
        from telegram.ext._picklepersistence import _BotUnpickler

        try:
            raw = filepath.read_bytes()
        except OSError:
            return None
        if not raw:
            return None
        if _is_plaintext_pickle(raw):
            buf = io.BytesIO(raw)
        else:
            try:
                buf = io.BytesIO(self._fernet.decrypt(raw))
            except InvalidToken:
                return None
        return _BotUnpickler(self.bot, buf).load()

    def _dump_file(self, filepath: Path, data: object) -> None:
        from telegram.ext._picklepersistence import _BotPickler

        buf = io.BytesIO()
        _BotPickler(self.bot, buf, protocol=pickle.HIGHEST_PROTOCOL).dump(data)
        encrypted = self._fernet.encrypt(buf.getvalue())
        tmp_path = Path(f"{filepath}.tmp")
        with tmp_path.open("wb") as f:
            f.write(encrypted)
        os.replace(str(tmp_path), str(filepath))
