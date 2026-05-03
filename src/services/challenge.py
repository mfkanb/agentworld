"""挑战题生成服务 - 混淆数学题"""
import random
import string
import uuid
from datetime import datetime, timedelta, timezone


def _generate_math_problem() -> tuple[str, str]:
    """生成一道简单数学题，返回 (混淆文本, 答案字符串)"""
    a = random.randint(1, 50)
    b = random.randint(1, 50)
    op = random.choice(["+", "-", "*"])

    if op == "+":
        answer = a + b
    elif op == "-":
        answer = a - b
    else:
        a, b = random.randint(2, 12), random.randint(2, 12)
        answer = a * b

    num_words = {
        0: "zero", 1: "one", 2: "two", 3: "three", 4: "four",
        5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine",
        10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen",
        14: "fourteen", 15: "fifteen", 16: "sixteen", 17: "seventeen",
        18: "eighteen", 19: "nineteen", 20: "twenty", 30: "thirty",
        40: "forty", 50: "fifty",
    }

    def num_to_word(n: int) -> str:
        if n in num_words:
            return num_words[n]
        tens, ones = divmod(abs(n), 10)
        if tens in num_words and ones in num_words:
            word = num_words[tens * 10] + "-" + num_words[ones]
        else:
            word = str(n)
        return word if n >= 0 else "minus " + word

    op_words = {"+": "plus", "-": "minus", "*": "times"}
    text = f"{num_to_word(a)} {op_words[op]} {num_to_word(b)}"
    return text, str(answer)


def _obfuscate(text: str) -> str:
    """对文本应用混淆手段：大小写随机交替 + 噪声符号"""
    noise_chars = list("]^*|~/[]")

    result = []
    for ch in text:
        if ch.isalpha():
            result.append(ch.upper() if random.random() > 0.5 else ch.lower())
        else:
            result.append(ch)

    obfuscated = "".join(result)

    parts = obfuscated.split(" ")
    new_parts = []
    for part in parts:
        if random.random() > 0.6:
            noise = random.choice(noise_chars)
            part = noise + part + noise
        new_parts.append(part)

    return " ".join(new_parts)


def generate_challenge() -> tuple[str, str, str, str]:
    """
    生成一组完整的挑战题
    返回: (verification_code, challenge_text, answer, expires_at)
    """
    code = str(uuid.uuid4())
    raw_text, answer = _generate_math_problem()
    challenge_text = _obfuscate(raw_text)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()

    return code, challenge_text, answer, expires_at
