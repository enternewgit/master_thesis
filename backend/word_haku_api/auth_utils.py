import jwt
from fastapi import HTTPException
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from decouple import config
from bson import ObjectId


JWT_KEY = config('JWT_KEY')

class AuthJwtCsrf():
    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    secret_key = JWT_KEY

    def generate_hashed_pw(self, password) -> str:
        return self.pwd_ctx.hash(password)
    
    def verify_pw(self, plain_pw, hashed_pw) -> bool:
        return self.pwd_ctx.verify(plain_pw, hashed_pw)
    
    def encode_jwt(self, login_id, role) -> str:
        payload = {
            'exp': datetime.now(timezone.utc) + timedelta(days=0, minutes=60),
            'iat': datetime.now(timezone.utc),
            'sub': login_id,
            'role': role
        }
        return jwt.encode(
            payload,
            self.secret_key,
            algorithm='HS256'
        )
    
    def decode_jwt(self, token) -> str:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            return payload['sub']
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=401, detail='The JWT has expired')
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=401, detail='JWT is not valid')
    
    def verify_jwt(self, request) -> str:
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(
                status_code=401, detail='No JWT exist: may not set yet or deleted')
        _, _, value = token.partition(" ")
        subject = self.decode_jwt(value)
        return subject
    
    async def verify_update_jwt(self, request) -> tuple[str, str]:
        from word_haku_api.databasev2 import db_get_username_by_login_id
        subject = self.verify_jwt(request)
        user = await db_get_username_by_login_id(subject)
        if not user:
            raise HTTPException(status_code=404, detail="ユーザが見つかりません")
        role = user.get("role", "user")
        new_token = self.encode_jwt(subject, role)
        return new_token, subject
    
    async def verify_csrf_update_jwt(self, request, csrf_protect, headers) -> str:
        from word_haku_api.databasev2 import db_get_username_by_login_id
        csrf_token = csrf_protect.get_csrf_from_headers(headers)
        csrf_protect.validate_csrf(csrf_token)
        subject = self.verify_jwt(request)
        user = await db_get_username_by_login_id(subject)
        if not user:
            raise HTTPException(status_code=404, detail="ユーザが見つかりません")
        role = user.get("role", "user")
        new_token = self.encode_jwt(subject, role)
        return new_token
    
    # 未ログインのユーザについて，CSRFトークンの検証のみを行う
    def verify_csrf(self, request, csrf_protect, headers):
        csrf_token = csrf_protect.get_csrf_from_headers(headers)
        csrf_protect.validate_csrf(csrf_token)
        return True