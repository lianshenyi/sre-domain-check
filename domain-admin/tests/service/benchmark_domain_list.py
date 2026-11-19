from collections import Counter
from statistics import median
from time import perf_counter, sleep
from types import SimpleNamespace

from flask import Flask, g
from peewee import SqliteDatabase

from domain_admin.api.domain_api import get_domain_list
from domain_admin.enums.role_enum import RoleEnum
from domain_admin.model.address_model import AddressModel
from domain_admin.model.domain_info_model import DomainInfoModel
from domain_admin.model.domain_model import DomainModel
from domain_admin.model.group_model import GroupModel
from domain_admin.model.group_user_model import GroupUserModel


class DelayedDatabase(SqliteDatabase):
    delay = 0

    def execute_sql(self, sql, params=None, **kwargs):
        if self.delay and sql.startswith('SELECT'):
            self.counts['SELECT'] += 1
            if 'FROM "tb_group_user"' in sql:
                self.counts['group membership'] += 1
            sleep(self.delay)
        return super().execute_sql(sql, params, **kwargs)


def main():
    database = DelayedDatabase(':memory:')
    models = [DomainModel, AddressModel, DomainInfoModel, GroupModel, GroupUserModel]
    app = Flask(__name__)
    with database.bind_ctx(models), database.connection_context():
        database.create_tables(models)
        GroupUserModel.create(user_id=1, group_id=1, has_edit_permission=True)
        for offset in range(0, 10000, 100):
            DomainModel.insert_many([
                dict(user_id=idx % 4 + 1, group_id=idx % 3, domain=f'd{idx}.example.test')
                for idx in range(offset, offset + 100)
            ]).execute()

        database.delay = 0.002
        for page in (5, 1000):
            samples = []
            for _ in range(31):
                database.counts = Counter()
                with app.test_request_context(json={'page': page, 'size': 50, 'role': RoleEnum.USER}):
                    g.user_id = 1
                    g.current_user_row = SimpleNamespace(role=RoleEnum.USER)
                    started = perf_counter()
                    result = get_domain_list.__wrapped__()
                    samples.append((perf_counter() - started) * 1000)
                    assert result['total'] == 5000
                    assert len(result['list']) == (50 if page == 5 else 0)
            print(f'page={page}: median={median(samples[1:]):.2f}ms, {dict(database.counts)}')


if __name__ == '__main__':
    main()
