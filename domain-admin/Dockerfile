ARG BASE_IMAGE=domain-admin-base:deps-dcb7d8c888558c95
FROM ${BASE_IMAGE}

COPY . /app

CMD ["gunicorn", "--bind", "[::]:8000", "--timeout", "120", "domain_admin.main:app"]
