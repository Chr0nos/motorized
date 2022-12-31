from motorized import Document


class User(Document):
    name: str
    is_admin: bool = False
