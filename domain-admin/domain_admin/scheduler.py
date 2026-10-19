# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals, absolute_import, division

from domain_admin.model.database import init_database
from domain_admin.service import scheduler_service
from domain_admin.service.system_service import init_system_config
from domain_admin.utils.flask_ext.flask_app import FlaskApp


app = FlaskApp(import_name=__name__)


def main():
    init_database()
    init_system_config(app)
    scheduler_service.init_scheduler()

    try:
        while True:
            import time
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
