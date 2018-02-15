import getpass
import os
import secrets
from pathlib import Path
from stat import S_IREAD

import keyring
from keyring.errors import PasswordDeleteError

SVC_NAME_KEY_FILE = Path(__file__).resolve().parent / 'service.txt'


class CredentialsError(Exception):
    pass


class Credentials:
    def __init__(self, file_path: Path = SVC_NAME_KEY_FILE,
                 username_prompt: str = "Username:",
                 password_prompt: str = "Password:"):
        self.svc_name_file_path = file_path
        self.username_prompt = username_prompt
        self.password_prompt = password_prompt

    @property
    def have_creds(self) -> bool:
        return all(self.get_login_from_key_store())

    @property
    def creds(self):
        if self.have_creds:
            return self.get_login_from_key_store()
        else:
            return None, None

    @property
    def svc_name(self):
        return self._get_svc_name()

    def delete_creds(self):
        if self.have_creds:
            errs = []
            try:
                keyring.delete_password(self.svc_name, 'password')
            except PasswordDeleteError:
                errs.append('password')

            try:
                keyring.delete_password(self.svc_name, 'username')
            except PasswordDeleteError:
                errs.append('username')

            if errs:
                raise CredentialsError(f'Unable to delete stored data: {errs}')

    def get_login_from_user(self):
        username = input(self.username_prompt)
        password = getpass.getpass(prompt=self.password_prompt)

        keyring.set_password(self.svc_name, 'username', username)
        keyring.set_password(self.svc_name, 'password', password)

    def get_login_from_key_store(self):
        return (keyring.get_password(self.svc_name, 'username'),
                keyring.get_password(self.svc_name, 'password'))

    def _make_svc_name_file(self):
        """Creates a file containing a random string.

        The purpose of this random string is to obfuscate the login credentials a bit to prevent a
        malicious application that has hoovered up all credentials in your system credentials store
        from knowing which service/key this application's stored credentials are stored with."""

        if not self.svc_name_file_path.is_file():
            self.svc_name_file_path.write_text(secrets.token_urlsafe(), encoding='utf8')
            os.chmod(str(self.svc_name_file_path), S_IREAD)

    def _get_svc_name(self):
        if not self.svc_name_file_path.exists():
            self._make_svc_name_file()
        return self.svc_name_file_path.read_text(encoding='utf8').strip()
