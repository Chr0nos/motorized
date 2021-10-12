class Criteria:
    def __init__(self, value=None):
        self.value = value

    def __hash__(self):
        return hash(self.name)

    def command(self, invert=False) -> str:
        raise NotImplementedError('override this')

    def get_value(self, invert=False):
        return self.value

    def as_mongo_expression(self, invert=False):
        return {self.command(invert): self.get_value(invert)}


class Eq(Criteria):
    def command(self, invert=False):
        return '$eq' if not invert else '$ne'


class Neq(Criteria):
    def command(self, invert=False):
        return '$ne' if not invert else '$eq'


class In(Criteria):
    def command(self, invert=False):
        return '$in' if not invert else '$nin'


class Nin(Criteria):
    def command(self, invert=False):
        return '$nin' if not invert else '$in'


class Gt(Criteria):
    def command(self, invert=False):
        return '$gt' if not invert else '$lte'


class Lt(Criteria):
    def command(self, invert=False):
        return '$lt' if not invert else '$gte'


class Lte(Criteria):
    def command(self, invert=False):
        return '$lte' if not invert else '$gt'


class Gte(Criteria):
    def command(self, invert=False):
        return '$gte' if not invert else '$lt'


class Exists(Criteria):
    def command(self, invert=False):
        return '$exists'

    def get_value(self, invert=False):
        if invert:
            return self.value is False
        return self.value


class Regex(Criteria):
    def command(self, invert=False):
        return '$regex'

    def get_value(self, invert=False):
        if not invert:
            return self.value
        raise NotImplementedError('Inverting regex is not implemented yet')
