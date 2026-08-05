import base64
import typing
import pydantic
import urdhva_base
import cryptography.fernet
from pydantic_core import core_schema
from pydantic.json_schema import JsonSchemaValue
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


class Secret(str):
    @classmethod
    def __get_pydantic_json_schema__(cls, _core_schema: typing.Any, handler: typing.Any) -> JsonSchemaValue:
        field_schema = handler(core_schema.str_schema())
        field_schema.update({"type": "string", "writeOnly": True, "format": "password"})
        return field_schema

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: typing.Any, handler: typing.Any) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls.validate,
            core_schema.str_schema(),
        )

    @classmethod
    def get_key(cls, domain: typing.Optional[str] = None) -> bytes:
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=None,
            backend=default_backend()
        )
        if not domain:
            password = urdhva_base.ctx['entity_id'] if urdhva_base.ctx.exists() else "urdhva_secret"
        else:
            password = domain
        return base64.urlsafe_b64encode(hkdf.derive(password.encode()))

    @classmethod
    def validate(cls, value: typing.Any) -> 'Secret':
        if isinstance(value, cls):
            return value
        if isinstance(value, str) and not value.startswith('enc#_'):
            key = cls.get_key(getattr(urdhva_base.settings, 'password_salt', None))
            encrypted = cryptography.fernet.Fernet(key).encrypt(value.encode()).decode()
            value = 'enc#_' + encrypted
        return cls(value)

    def __repr__(self) -> str:
        return f"Secret('{self}')"

    def __eq__(self, other: typing.Any) -> bool:
        return isinstance(other, Secret) and self.get_secret() == other.get_secret()

    def get_secret(self, domain: typing.Optional[str] = None) -> str:
        if not self.startswith('enc#_'):
            return str(self)
        
        salt = domain or getattr(urdhva_base.settings, 'password_salt', None)
        key = self.get_key(salt)
        
        try:
            return cryptography.fernet.Fernet(key).decrypt(self[5:].encode()).decode()
        except cryptography.fernet.InvalidToken:
            # Fallback if decryption fails due to key mismatch
            return str(self)
