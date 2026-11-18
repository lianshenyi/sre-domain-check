# -*- coding: utf-8 -*-
from peewee import AutoField, CharField, DateTimeField, IntegerField

from domain_admin.model.base_model import BaseModel


class AgentNode(BaseModel):
    id = AutoField()
    name = CharField(max_length=64)
    region = CharField(max_length=64)
    enrollment_hash = CharField(max_length=64, null=True)
    enrollment_expires_at = DateTimeField(null=True)
    credential_hash = CharField(max_length=64, null=True)
    last_seen_at = DateTimeField(null=True)

    class Meta:
        table_name = 'tb_agent_node'


class AgentCheck(BaseModel):
    id = AutoField()
    batch_id = CharField(max_length=32)
    domain_id = IntegerField()
    domain_created_at = DateTimeField()
    domain = CharField()
    port = IntegerField()
    ssl_type = IntegerField()
    agent_id = IntegerField()
    status = CharField(max_length=16, default='queued')
    created_at = DateTimeField()
    deadline_at = DateTimeField()
    finished_at = DateTimeField(null=True)
    cert_starts_at = DateTimeField(null=True)
    cert_expires_at = DateTimeField(null=True)
    error = CharField(max_length=32, null=True)

    class Meta:
        table_name = 'tb_agent_check'
        indexes = (
            (('domain_id', 'id'), False),
            (('domain_id', 'batch_id', 'id'), False),
            (('agent_id', 'status', 'id'), False),
        )
