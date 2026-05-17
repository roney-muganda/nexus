from passlib.context import CryptContext

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12
)


def hash_password(password: str) -> str:
    # bcrypt has a 72-byte limit — truncate safely
    password = password[:72]
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    plain_password = plain_password[:72]
    return pwd_context.verify(plain_password, hashed_password)