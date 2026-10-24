"""真網發現 Telegram 會裁掉片段首尾空白，防止分段換行遺失。"""
import pytest

from tg_delivery import split_plaintext


@pytest.mark.parametrize('text,limit', [
    ('123456\nabcdefgh', 10),
    ('開始 '+('正體中文🌐🧪與換行\n'*510)+'結尾', 4096),
    ('alpha  beta\n\ngamma delta '*30+'結尾', 20),
], ids=['newline','unicode_emoji','spaces_and_blank_lines'])
def test_message_boundary_survives_server_whitespace_trimming(text, limit):
    pieces=split_plaintext(text,limit)
    assert ''.join(piece.strip() for piece in pieces)==text
    assert all(len(piece.encode('utf-16-le'))//2<=limit for piece in pieces)
