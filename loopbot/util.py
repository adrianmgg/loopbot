from typing import Union

def bot_invite_link(*, client_id: Union[str, int], permissions: Union[str, int]) -> str:
    from urllib.parse import urlencode
    querystr = urlencode({'client_id': client_id, 'permissions': permissions, 'scope': 'bot'})
    return f'https://discord.com/api/oauth2/authorize?{querystr}'
