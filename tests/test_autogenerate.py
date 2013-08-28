import re
import sys
from unittest import TestCase

from sqlalchemy import MetaData, Column, Table, Integer, String, Text, \
    Numeric, CHAR, ForeignKey, DATETIME, \
    TypeDecorator, CheckConstraint, Unicode, Enum,\
    UniqueConstraint, Boolean, ForeignKeyConstraint,\
    PrimaryKeyConstraint, Index, func
from sqlalchemy.types import NULLTYPE, TIMESTAMP
from sqlalchemy.dialects import mysql
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.sql import and_, column, literal_column

from alembic import autogenerate, util
from alembic.migration import MigrationContext
from . import staging_env, sqlite_db, clear_staging_env, eq_, \
        eq_ignore_whitespace, requires_07, db_for_dialect

py3k = sys.version_info >= (3, )

def _model_one(schema=None):
    m = MetaData(schema=schema)

    Table('user', m,
        Column('id', Integer, primary_key=True),
        Column('name', String(50)),
        Column('a1', Text),
        Column("pw", String(50))
    )

    Table('address', m,
        Column('id', Integer, primary_key=True),
        Column('email_address', String(100), nullable=False),
        Index('address_email_address_idx', 'email_address')
    )

    Table('order', m,
        Column('order_id', Integer, primary_key=True),
        Column("amount", Numeric(8, 2), nullable=False,
                server_default="0"),
        CheckConstraint('amount >= 0', name='ck_order_amount')
    )

    Table('extra', m,
        Column("x", CHAR),
        Column('uid', Integer, ForeignKey('user.id'))
    )

    return m

def _model_two(schema=None):
    m = MetaData(schema=schema)

    Table('user', m,
        Column('id', Integer, primary_key=True),
        Column('name', String(50), nullable=False, index=True),
        Column('a1', Text, server_default="x")
    )

    Table('address', m,
        Column('id', Integer, primary_key=True),
        Column('email_address', String(100), unique=True, nullable=False),
        Column('street', String(50))
    )

    Table('order', m,
        Column('order_id', Integer, primary_key=True),
        Column('amount', Numeric(10, 2), nullable=True,
                    server_default="0"),
        Column('user_id', Integer, ForeignKey('user.id')),
        CheckConstraint('amount > -1', name='ck_order_amount'),
        UniqueConstraint('order_id', 'user_id', 
            name='order_order_id_user_id_unique'
        ),
        Index('order_user_id_amount_idx', 'user_id', 'amount')
    )

    Table('item', m,
        Column('id', Integer, primary_key=True),
        Column('description', String(100)),
        Column('order_id', Integer, ForeignKey('order.order_id')),
        CheckConstraint("'len(description) > 5'")
    )
    return m

def _model_five(schema=None):
    m = MetaData(schema=schema)

    Table('user', m,
        Column('id', Integer, primary_key=True),
        Column('name', String(50), nullable=False, unique=True),
        Column('a1', Text, server_default="x")
    )

    Table('address', m,
        Column('id', Integer, primary_key=True),
        Column('email_address', String(100), unique=True, nullable=False),
        Column('street', String(50))
    )

    Table('order', m,
        Column('order_id', Integer, primary_key=True),
        Column('amount', Numeric(10, 2), nullable=True,
                    server_default="0"),
        Column('user_id', Integer, ForeignKey('user.id')),
        UniqueConstraint('order_id', 'user_id', 
            name='order_order_id_user_id_unique'
        ),
        Index('order_user_id_amount_idx', 'user_id', 'amount', unique=True)
    )

    Table('item', m,
        Column('id', Integer, primary_key=True),
        Column('description', String(100)),
        Column('order_id', Integer, ForeignKey('order.order_id')),
        CheckConstraint("'len(description) > 5'")
    )
    return m

def _model_three():
    m = MetaData()
    return m

def _model_four():
    m = MetaData()

    Table('parent', m,
        Column('id', Integer, primary_key=True)
    )

    Table('child', m,
        Column('parent_id', Integer, ForeignKey('parent.id')),
    )

    return m

def _default_include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table":
        return name in ("parent", "child",
                                "user", "order", "item",
                                "address", "extra")
    else:
        return True

_default_object_filters = [
    _default_include_object
]

class AutogenTest(object):
    @classmethod
    def _get_bind(cls):
        return sqlite_db()

    @classmethod
    @requires_07
    def setup_class(cls):
        staging_env()
        cls.bind = cls._get_bind()
        cls.m1 = cls._get_db_schema()
        cls.m1.create_all(cls.bind)
        cls.m2 = cls._get_model_schema()

        conn = cls.bind.connect()
        cls.context = context = MigrationContext.configure(
            connection=conn,
            opts={
                'compare_type': True,
                'compare_server_default':True,
                'target_metadata':cls.m2,
                'upgrade_token':"upgrades",
                'downgrade_token':"downgrades",
                'alembic_module_prefix':'op.',
                'sqlalchemy_module_prefix':'sa.',
            }
        )

        connection = context.bind
        cls.autogen_context = {
            'imports':set(),
            'connection':connection,
            'dialect':connection.dialect,
            'context':context
            }

    @classmethod
    def teardown_class(cls):
        cls.m1.drop_all(cls.bind)
        clear_staging_env()


class ImplicitConstraintNoGenTest(AutogenTest, TestCase):

    @classmethod
    def _get_bind(cls):
        return db_for_dialect('mysql') #sqlite_db()

    @classmethod
    def _get_db_schema(cls):
        m = MetaData()

        Table('someothertable', m,
            Column('id', Integer, primary_key=True),
            Column('value', Boolean()),
            mysql_engine='InnoDB',
            mysql_default_charset='utf8'
        )
        return m

    @classmethod
    def _get_model_schema(cls):
        m = MetaData()

        Table('sometable', m,
            Column('id', Integer, primary_key=True),
            Column('value', Boolean()),
        )
        return m


    def test_boolean_gen_upgrade(self):
        template_args = {}
        autogenerate._produce_migration_diffs(self.context,
            template_args, set(),
            include_symbol=lambda name, schema=None: name == 'sometable')
        eq_(
            re.sub(r"u'", "'", template_args['upgrades']),
            "### commands auto generated by Alembic - please adjust! ###\n"
            "    op.create_table('sometable',\n"
            "    sa.Column('id', sa.Integer(), nullable=False),\n"
            "    sa.Column('value', sa.Boolean(), nullable=True),\n"
            "    sa.PrimaryKeyConstraint('id')\n    )\n"
            "    ### end Alembic commands ###"
        )

    def test_boolean_gen_downgrade(self):
        # on the downgrade side, we are OK for now, as SQLAlchemy
        # does not reflect check constraints yet.

        template_args = {}
        autogenerate._produce_migration_diffs(self.context,
            template_args, set(),
            include_symbol=lambda name, schema=None: name in ('sometable', 'someothertable')
            )
        eq_(
            re.sub(r"u'", "'", template_args['downgrades']),
            "### commands auto generated by Alembic - please adjust! ###\n"
            "    op.create_table('someothertable',\n"
            "    sa.Column('id', mysql.INTEGER(display_width=11), "
                "nullable=False),\n"
            "    sa.Column('value', mysql.TINYINT(display_width=1), "
            "autoincrement=False, nullable=True),\n"
            "    sa.PrimaryKeyConstraint('id'),\n"
            "    mysql_default_charset='utf8',\n"
            "    mysql_engine='InnoDB'\n"
            "    )\n"
            "    op.drop_table('sometable')\n"
            "    ### end Alembic commands ###"
        )


class AutogenCrossSchemaTest(AutogenTest, TestCase):
    @classmethod
    def _get_bind(cls):
        cls.test_schema_name = "test_schema"
        return db_for_dialect('postgresql')

    @classmethod
    def _get_db_schema(cls):
        m = MetaData()
        Table('t1', m,
                Column('x', Integer)
            )
        Table('t2', m,
                Column('y', Integer),
                schema=cls.test_schema_name
            )
        return m

    @classmethod
    def _get_model_schema(cls):
        m = MetaData()
        Table('t3', m,
                Column('q', Integer)
            )
        Table('t4', m,
                Column('z', Integer),
                schema=cls.test_schema_name
            )
        return m

    def test_default_schema_omitted_upgrade(self):
        metadata = self.m2
        connection = self.context.bind
        diffs = []
        def include_object(obj, name, type_, reflected, compare_to):
            if type_ == "table":
                return name == "t3"
            else:
                return True
        autogenerate._produce_net_changes(connection, metadata, diffs,
                                          self.autogen_context,
                                          object_filters=[include_object],
                                          include_schemas=True
                                          )
        eq_(diffs[0][0], "add_table")
        eq_(diffs[0][1].schema, None)

    def test_alt_schema_included_upgrade(self):
        metadata = self.m2
        connection = self.context.bind
        diffs = []
        def include_object(obj, name, type_, reflected, compare_to):
            if type_ == "table":
                return name == "t4"
            else:
                return True
        autogenerate._produce_net_changes(connection, metadata, diffs,
                                          self.autogen_context,
                                          object_filters=[include_object],
                                          include_schemas=True
                                          )
        eq_(diffs[0][0], "add_table")
        eq_(diffs[0][1].schema, self.test_schema_name)

    def test_default_schema_omitted_downgrade(self):
        metadata = self.m2
        connection = self.context.bind
        diffs = []
        def include_object(obj, name, type_, reflected, compare_to):
            if type_ == "table":
                return name == "t1"
            else:
                return True
        autogenerate._produce_net_changes(connection, metadata, diffs,
                                          self.autogen_context,
                                          object_filters=[include_object],
                                          include_schemas=True
                                          )
        eq_(diffs[0][0], "remove_table")
        eq_(diffs[0][1].schema, None)

    def test_alt_schema_included_downgrade(self):
        metadata = self.m2
        connection = self.context.bind
        diffs = []
        def include_object(obj, name, type_, reflected, compare_to):
            if type_ == "table":
                return name == "t2"
            else:
                return True
        autogenerate._produce_net_changes(connection, metadata, diffs,
                                          self.autogen_context,
                                          object_filters=[include_object],
                                          include_schemas=True
                                          )
        eq_(diffs[0][0], "remove_table")
        eq_(diffs[0][1].schema, self.test_schema_name)




class AutogenerateDiffTestWSchema(AutogenTest, TestCase):

    @classmethod
    def _get_bind(cls):
        cls.test_schema_name = "test_schema"
        return db_for_dialect('postgresql')

    @classmethod
    def _get_db_schema(cls):
        return _model_one(schema=cls.test_schema_name)

    @classmethod
    def _get_model_schema(cls):
        return _model_two(schema=cls.test_schema_name)

    def test_diffs(self):
        """test generation of diff rules"""

        metadata = self.m2
        connection = self.context.bind
        diffs = []
        autogenerate._produce_net_changes(connection, metadata, diffs,
                                          self.autogen_context,
                                          object_filters=_default_object_filters,
                                          include_schemas=True
                                          )

        eq_(
            diffs[0],
            ('add_table', metadata.tables['%s.item' % self.test_schema_name])
        )

        eq_(diffs[1][0], 'remove_table')
        eq_(diffs[1][1].name, "extra")

        eq_(diffs[2][0], "add_column")
        eq_(diffs[2][1], self.test_schema_name)
        eq_(diffs[2][2], "address")
        eq_(diffs[2][3], metadata.tables['%s.address' % self.test_schema_name].c.street)

        eq_(diffs[3][0], "add_constraint")

        eq_(diffs[4][0], "add_column")
        eq_(diffs[4][1], self.test_schema_name)
        eq_(diffs[4][2], "order")
        eq_(diffs[4][3], metadata.tables['%s.order' % self.test_schema_name].c.user_id)

        eq_(diffs[5][0][0], "modify_type")
        eq_(diffs[5][0][1], self.test_schema_name)
        eq_(diffs[5][0][2], "order")
        eq_(diffs[5][0][3], "amount")
        eq_(repr(diffs[5][0][5]), "NUMERIC(precision=8, scale=2)")
        eq_(repr(diffs[5][0][6]), "Numeric(precision=10, scale=2)")

        eq_(diffs[6][0], "add_constraint")
        eq_(diffs[6][1].name, "order_order_id_user_id_unique")


        eq_(diffs[7][0], "add_index")
        eq_(diffs[7][1].name, "order_user_id_amount_idx")

        eq_(diffs[8][0], 'remove_column')
        eq_(diffs[8][3].name, 'pw')

        eq_(diffs[9][0][0], "modify_default")
        eq_(diffs[9][0][1], self.test_schema_name)
        eq_(diffs[9][0][2], "user")
        eq_(diffs[9][0][3], "a1")
        eq_(diffs[9][0][6].arg, "x")

        eq_(diffs[10][0][0], 'modify_nullable')
        eq_(diffs[10][0][5], True)
        eq_(diffs[10][0][6], False)

    def test_render_nothing(self):
        context = MigrationContext.configure(
            connection=self.bind.connect(),
            opts={
                'compare_type': True,
                'compare_server_default': True,
                'target_metadata': self.m1,
                'upgrade_token': "upgrades",
                'downgrade_token': "downgrades",
                'alembic_module_prefix': 'op.',
                'sqlalchemy_module_prefix': 'sa.',
            }
        )
        template_args = {}
        autogenerate._produce_migration_diffs(context, template_args, set(),
                include_symbol=lambda name, schema: False
            )
        eq_(re.sub(r"u'", "'", template_args['upgrades']),
"""### commands auto generated by Alembic - please adjust! ###
    pass
    ### end Alembic commands ###""")
        eq_(re.sub(r"u'", "'", template_args['downgrades']),
"""### commands auto generated by Alembic - please adjust! ###
    pass
    ### end Alembic commands ###""")

    def test_render_diffs_extras(self):
        """test a full render including indentation (include and schema)"""

        template_args = {}
        autogenerate._produce_migration_diffs(
                        self.context, template_args, set(),
                        include_object=_default_include_object,
                        include_schemas=True
                        )

        eq_(re.sub(r"u'", "'", template_args['upgrades']),
"""### commands auto generated by Alembic - please adjust! ###
    op.create_table('item',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('description', sa.String(length=100), nullable=True),
    sa.Column('order_id', sa.Integer(), nullable=True),
    sa.CheckConstraint("'len(description) > 5'"),
    sa.ForeignKeyConstraint(['order_id'], ['%(schema)s.order.order_id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='%(schema)s'
    )
    op.drop_table('extra', schema='%(schema)s')
    op.add_column('address', sa.Column('street', sa.String(length=50), nullable=True), schema='%(schema)s')
    op.create_unique_constraint('uq_test_schema_address_email_address', 'test_schema.address', ['email_address'], schema='test_schema')
    op.add_column('order', sa.Column('user_id', sa.Integer(), nullable=True), schema='%(schema)s')
    op.alter_column('order', 'amount',
               existing_type=sa.NUMERIC(precision=8, scale=2),
               type_=sa.Numeric(precision=10, scale=2),
               nullable=True,
               existing_server_default='0::numeric',
               schema='%(schema)s')
    op.create_unique_constraint('order_order_id_user_id_unique', 'test_schema.order', ['order_id', 'user_id'], schema='test_schema')
    op.create_index('order_user_id_amount_idx', 'test_schema.order', ['user_id', 'amount'], unique=False, schema='test_schema')
    op.drop_column('user', 'pw', schema='%(schema)s')
    op.alter_column('user', 'a1',
               existing_type=sa.TEXT(),
               server_default='x',
               existing_nullable=True,
               schema='%(schema)s')
    op.alter_column('user', 'name',
               existing_type=sa.VARCHAR(length=50),
               nullable=False,
               schema='%(schema)s')
    op.create_index('ix_test_schema_user_name', 'test_schema.user', ['name'], unique=False, schema='test_schema')
    ### end Alembic commands ###""" % {"schema": self.test_schema_name})
        eq_(re.sub(r"u'", "'", template_args['downgrades']),
"""### commands auto generated by Alembic - please adjust! ###
    op.drop_index('ix_test_schema_user_name', 'test_schema.user')
    op.alter_column('user', 'name',
               existing_type=sa.VARCHAR(length=50),
               nullable=True,
               schema='%(schema)s')
    op.alter_column('user', 'a1',
               existing_type=sa.TEXT(),
               server_default=None,
               existing_nullable=True,
               schema='%(schema)s')
    op.add_column('user', sa.Column('pw', sa.VARCHAR(length=50), nullable=True), schema='%(schema)s')
    op.drop_index('order_user_id_amount_idx', 'test_schema.order')
    op.drop_constraint('order_order_id_user_id_unique', 'test_schema.order')
    op.alter_column('order', 'amount',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.NUMERIC(precision=8, scale=2),
               nullable=False,
               existing_server_default='0::numeric',
               schema='%(schema)s')
    op.drop_column('order', 'user_id', schema='%(schema)s')
    op.drop_constraint('uq_test_schema_address_email_address', 'test_schema.address')
    op.drop_column('address', 'street', schema='%(schema)s')
    op.create_table('extra',
    sa.Column('x', sa.CHAR(length=1), autoincrement=False, nullable=True),
    sa.Column('uid', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['uid'], ['%(schema)s.user.id'], name='extra_uid_fkey'),
    sa.PrimaryKeyConstraint(),
    schema='%(schema)s'
    )
    op.drop_table('item', schema='%(schema)s')
    ### end Alembic commands ###""" % {"schema": self.test_schema_name})


class AutogenerateDiffTest(AutogenTest, TestCase):
    @classmethod
    def _get_db_schema(cls):
        return _model_one()

    @classmethod
    def _get_model_schema(cls):
        return _model_two()

    def test_diffs(self):
        """test generation of diff rules"""

        metadata = self.m2
        connection = self.context.bind
        diffs = []
        autogenerate._produce_net_changes(connection, metadata, diffs,
                                          self.autogen_context,
                                          object_filters=_default_object_filters,
                                    )

        eq_(
            diffs[0],
            ('add_table', metadata.tables['item'])
        )

        eq_(diffs[1][0], 'remove_table')
        eq_(diffs[1][1].name, "extra")

        eq_(diffs[2][0], "add_column")
        eq_(diffs[2][1], None)
        eq_(diffs[2][2], "address")
        eq_(diffs[2][3], metadata.tables['address'].c.street)

        eq_(diffs[4][0], "remove_index")
        eq_(diffs[4][1].name, "address_email_address_idx")

        eq_(diffs[5][0], "add_column")
        eq_(diffs[5][1], None)
        eq_(diffs[5][2], "order")
        eq_(diffs[5][3], metadata.tables['order'].c.user_id)

        eq_(diffs[6][0][0], "modify_type")
        eq_(diffs[6][0][1], None)
        eq_(diffs[6][0][2], "order")
        eq_(diffs[6][0][3], "amount")
        eq_(repr(diffs[6][0][5]), "NUMERIC(precision=8, scale=2)")
        eq_(repr(diffs[6][0][6]), "Numeric(precision=10, scale=2)")

        eq_(diffs[7][0], "add_constraint")
        eq_(diffs[7][1].name, "order_order_id_user_id_unique")

        eq_(diffs[8][0], 'add_index')
        eq_(diffs[8][1].name, 'order_user_id_amount_idx')

        eq_(diffs[9][0], 'remove_column')
        eq_(diffs[9][3].name, 'pw')

        eq_(diffs[10][0][0], "modify_default")
        eq_(diffs[10][0][1], None)
        eq_(diffs[10][0][2], "user")
        eq_(diffs[10][0][3], "a1")
        eq_(diffs[10][0][6].arg, "x")

        eq_(diffs[11][0][0], 'modify_nullable')
        eq_(diffs[11][0][5], True)
        eq_(diffs[11][0][6], False)

    def test_render_nothing(self):
        context = MigrationContext.configure(
            connection=self.bind.connect(),
            opts={
                'compare_type': True,
                'compare_server_default': True,
                'target_metadata': self.m1,
                'upgrade_token': "upgrades",
                'downgrade_token': "downgrades",
            }
        )
        template_args = {}
        autogenerate._produce_migration_diffs(context, template_args, set())

        eq_(re.sub(r"u'", "'", template_args['upgrades']),
"""### commands auto generated by Alembic - please adjust! ###
    pass
    ### end Alembic commands ###""")
        eq_(re.sub(r"u'", "'", template_args['downgrades']),
"""### commands auto generated by Alembic - please adjust! ###
    pass
    ### end Alembic commands ###""")

    def test_render_diffs_standard(self):
        """test a full render including indentation"""

        metadata = self.m2
        template_args = {}
        autogenerate._produce_migration_diffs(self.context, template_args, set())

        eq_(re.sub(r"u'", "'", template_args['upgrades']),
"""### commands auto generated by Alembic - please adjust! ###
    op.create_table('item',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('description', sa.String(length=100), nullable=True),
    sa.Column('order_id', sa.Integer(), nullable=True),
    sa.CheckConstraint("'len(description) > 5'"),
    sa.ForeignKeyConstraint(['order_id'], ['order.order_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.drop_table('extra')
    op.add_column('address', sa.Column('street', sa.String(length=50), nullable=True))
    op.create_unique_constraint('uq_address_email_address', 'address', ['email_address'])
    op.drop_index('address_email_address_idx', 'address')
    op.add_column('order', sa.Column('user_id', sa.Integer(), nullable=True))
    op.alter_column('order', 'amount',
               existing_type=sa.NUMERIC(precision=8, scale=2),
               type_=sa.Numeric(precision=10, scale=2),
               nullable=True,
               existing_server_default='0')
    op.create_unique_constraint('order_order_id_user_id_unique', 'order', ['order_id', 'user_id'])
    op.create_index('order_user_id_amount_idx', 'order', ['user_id', 'amount'], unique=False)
    op.drop_column('user', 'pw')
    op.alter_column('user', 'a1',
               existing_type=sa.TEXT(),
               server_default='x',
               existing_nullable=True)
    op.alter_column('user', 'name',
               existing_type=sa.VARCHAR(length=50),
               nullable=False)
    op.create_index('ix_user_name', 'user', ['name'], unique=False)
    ### end Alembic commands ###""")
        eq_(re.sub(r"u'", "'", template_args['downgrades']),
"""### commands auto generated by Alembic - please adjust! ###
    op.drop_index('ix_user_name', 'user')
    op.alter_column('user', 'name',
               existing_type=sa.VARCHAR(length=50),
               nullable=True)
    op.alter_column('user', 'a1',
               existing_type=sa.TEXT(),
               server_default=None,
               existing_nullable=True)
    op.add_column('user', sa.Column('pw', sa.VARCHAR(length=50), nullable=True))
    op.drop_index('order_user_id_amount_idx', 'order')
    op.drop_constraint('order_order_id_user_id_unique', 'order')
    op.alter_column('order', 'amount',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.NUMERIC(precision=8, scale=2),
               nullable=False,
               existing_server_default='0')
    op.drop_column('order', 'user_id')
    op.create_index('address_email_address_idx', 'address', ['email_address'], unique=False)
    op.drop_constraint('uq_address_email_address', 'address')
    op.drop_column('address', 'street')
    op.create_table('extra',
    sa.Column('x', sa.CHAR(), nullable=True),
    sa.Column('uid', sa.INTEGER(), nullable=True),
    sa.ForeignKeyConstraint(['uid'], ['user.id'], ),
    sa.PrimaryKeyConstraint()
    )
    op.drop_table('item')
    ### end Alembic commands ###""")

    def test_include_symbol(self):
        context = MigrationContext.configure(
            connection=self.bind.connect(),
            opts={
                'compare_type': True,
                'compare_server_default': True,
                'target_metadata': self.m2,
                'include_symbol': lambda name, schema=None:
                                    name in ('address', 'order'),
                'upgrade_token': "upgrades",
                'downgrade_token': "downgrades",
                'alembic_module_prefix': 'op.',
                'sqlalchemy_module_prefix': 'sa.',
            }
        )
        template_args = {}
        autogenerate._produce_migration_diffs(context, template_args, set())
        template_args['upgrades'] = template_args['upgrades'].replace("u'", "'")
        template_args['downgrades'] = template_args['downgrades'].\
                                        replace("u'", "'")
        assert "alter_column('user'" not in template_args['upgrades']
        assert "alter_column('user'" not in template_args['downgrades']
        assert "alter_column('order'" in template_args['upgrades']
        assert "alter_column('order'" in template_args['downgrades']

    def test_include_object(self):
        def include_object(obj, name, type_, reflected, compare_to):
            assert obj.name == name
            if type_ == "table":
                if reflected:
                    assert obj.metadata is not self.m2
                else:
                    assert obj.metadata is self.m2
                return name in ("address", "order")
            elif type_ == "column":
                if reflected:
                    assert obj.table.metadata is not self.m2
                else:
                    assert obj.table.metadata is self.m2
                return name != "street"
            else:
                return True


        context = MigrationContext.configure(
            connection=self.bind.connect(),
            opts={
                'compare_type': True,
                'compare_server_default': True,
                'target_metadata': self.m2,
                'include_object': include_object,
                'upgrade_token': "upgrades",
                'downgrade_token': "downgrades",
                'alembic_module_prefix': 'op.',
                'sqlalchemy_module_prefix': 'sa.',
            }
        )
        template_args = {}
        autogenerate._produce_migration_diffs(context, template_args, set())
        template_args['upgrades'] = template_args['upgrades'].replace("u'", "'")
        template_args['downgrades'] = template_args['downgrades'].\
                                        replace("u'", "'")

        assert "alter_column('user'" not in template_args['upgrades']
        assert "alter_column('user'" not in template_args['downgrades']
        assert "'street'" not in template_args['upgrades']
        assert "'street'" not in template_args['downgrades']
        assert "alter_column('order'" in template_args['upgrades']
        assert "alter_column('order'" in template_args['downgrades']

    def test_skip_null_type_comparison_reflected(self):
        diff = []
        autogenerate._compare_type(None, "sometable", "somecol",
            Column("somecol", NULLTYPE),
            Column("somecol", Integer()),
            diff, self.autogen_context
        )
        assert not diff

    def test_skip_null_type_comparison_local(self):
        diff = []
        autogenerate._compare_type(None, "sometable", "somecol",
            Column("somecol", Integer()),
            Column("somecol", NULLTYPE),
            diff, self.autogen_context
        )
        assert not diff

    def test_affinity_typedec(self):
        class MyType(TypeDecorator):
            impl = CHAR

            def load_dialect_impl(self, dialect):
                if dialect.name == 'sqlite':
                    return dialect.type_descriptor(Integer())
                else:
                    return dialect.type_descriptor(CHAR(32))

        diff = []
        autogenerate._compare_type(None, "sometable", "somecol",
            Column("somecol", Integer, nullable=True),
            Column("somecol", MyType()),
            diff, self.autogen_context
        )
        assert not diff

    def test_dont_barf_on_already_reflected(self):
        diffs = []
        from sqlalchemy.util import OrderedSet
        inspector = Inspector.from_engine(self.bind)
        autogenerate._compare_tables(
            OrderedSet([(None, 'extra'), (None, 'user')]),
            OrderedSet(), [], inspector,
                MetaData(), diffs, self.autogen_context
        )
        eq_(
            [(rec[0], rec[1].name) for rec in diffs],
            [('remove_table', 'extra'), ('remove_table', 'user')]
        )


class AutogenerateDiffTestModelFive(AutogenTest, TestCase):

    @classmethod
    def _get_db_schema(cls):
        return _model_two()

    @classmethod
    def _get_model_schema(cls):
        return _model_five()

    @classmethod
    @requires_07
    def setup_class(cls):
        staging_env()
        cls.bind = cls._get_bind()
        cls.m2 = cls._get_db_schema()
        cls.m2.create_all(cls.bind)
        cls.m5 = cls._get_model_schema()

        conn = cls.bind.connect()
        cls.context = context = MigrationContext.configure(
            connection=conn,
            opts={
                'compare_type': True,
                'compare_server_default':True,
                'target_metadata':cls.m5,
                'upgrade_token':"upgrades",
                'downgrade_token':"downgrades",
                'alembic_module_prefix':'op.',
                'sqlalchemy_module_prefix':'sa.',
            }
        )

        connection = context.bind
        cls.autogen_context = {
            'imports':set(),
            'connection':connection,
            'dialect':connection.dialect,
            'context':context
            }

    @classmethod
    def teardown_class(cls):
        cls.m2.drop_all(cls.bind)
        clear_staging_env()

    def test_diffs(self):
        """test generation of diff rules"""

        metadata = self.m5
        connection = self.context.bind
        diffs = []
        autogenerate._produce_net_changes(connection, metadata, diffs,
                                          self.autogen_context,
                                          object_filters=_default_object_filters,
                                    )

        eq_(diffs[0][0], "add_constraint")
        eq_(diffs[0][1].table.name, "address")

        eq_(diffs[1][0], "remove_index")
        eq_(diffs[1][1].name, "order_user_id_amount_idx")
        eq_(diffs[1][1].unique, False)

        eq_(diffs[2][0], "add_index")
        eq_(diffs[2][1].name, "order_user_id_amount_idx")
        eq_(diffs[2][1].unique, True)

        eq_(diffs[3][0], "add_constraint")
        eq_(diffs[3][1].table.name, "user")

        eq_(diffs[4][0], "remove_index")
        eq_(diffs[4][1].name, "ix_user_name")


    def test_render_diffs_standard(self):
        """test a full render including indentation"""

        metadata = self.m5
        template_args = {}
        autogenerate._produce_migration_diffs(self.context, template_args, set())

        eq_(re.sub(r"u'", "'", template_args['upgrades']),
"""### commands auto generated by Alembic - please adjust! ###
    op.create_unique_constraint('uq_address_email_address', 'address', ['email_address'])
    op.drop_index('order_user_id_amount_idx', 'order')
    op.create_index('order_user_id_amount_idx', 'order', ['user_id', 'amount'], unique=True)
    op.create_unique_constraint('uq_user_name', 'user', ['name'])
    op.drop_index('ix_user_name', 'user')
    ### end Alembic commands ###""")
        eq_(re.sub(r"u'", "'", template_args['downgrades']),
"""### commands auto generated by Alembic - please adjust! ###
    op.create_index('ix_user_name', 'user', ['name'], unique=False)
    op.drop_constraint('uq_user_name', 'user')
    op.drop_index('order_user_id_amount_idx', 'order')
    op.create_index('order_user_id_amount_idx', 'order', ['user_id', 'amount'], unique=False)
    op.drop_constraint('uq_address_email_address', 'address')
    ### end Alembic commands ###""")


class AutogenKeyTest(AutogenTest, TestCase):
    @classmethod
    def _get_db_schema(cls):
        m = MetaData()

        Table('someothertable', m,
            Column('id', Integer, primary_key=True),
            Column('value', Integer, key="somekey"),
        )
        return m

    @classmethod
    def _get_model_schema(cls):
        m = MetaData()

        Table('sometable', m,
            Column('id', Integer, primary_key=True),
            Column('value', Integer, key="someotherkey"),
        )
        Table('someothertable', m,
            Column('id', Integer, primary_key=True),
            Column('value', Integer, key="somekey"),
            Column("othervalue", Integer, key="otherkey")
        )
        return m

    symbols = ['someothertable', 'sometable']
    def test_autogen(self):
        metadata = self.m2
        connection = self.context.bind

        diffs = []

        autogenerate._produce_net_changes(connection, metadata, diffs,
                                          self.autogen_context,
                                          include_schemas=False
                                          )
        eq_(diffs[0][0], "add_table")
        eq_(diffs[0][1].name, "sometable")
        eq_(diffs[1][0], "add_column")
        eq_(diffs[1][3].key, "otherkey")

class AutogenerateDiffOrderTest(TestCase):
    @classmethod
    @requires_07
    def setup_class(cls):
        staging_env()
        cls.bind = sqlite_db()
        cls.m3 = _model_three()
        cls.m3.create_all(cls.bind)
        cls.m4 = _model_four()

        cls.empty_context = empty_context = MigrationContext.configure(
            connection = cls.bind.connect(),
            opts = {
                'compare_type':True,
                'compare_server_default':True,
                'target_metadata':cls.m3,
                'upgrade_token':"upgrades",
                'downgrade_token':"downgrades",
                'alembic_module_prefix':'op.',
                'sqlalchemy_module_prefix':'sa.'
            }
        )

        connection = empty_context.bind
        cls.autogen_empty_context = {
            'imports': set(),
            'connection': connection,
            'dialect': connection.dialect,
            'context': empty_context
            }

    @classmethod
    def teardown_class(cls):
        clear_staging_env()

    def test_diffs_order(self):
        """
        Added in order to test that child tables(tables with FKs) are generated
        before their parent tables
        """

        metadata = self.m4
        connection = self.empty_context.bind
        diffs = []

        autogenerate._produce_net_changes(connection, metadata, diffs,
                                          self.autogen_empty_context)

        eq_(diffs[0][0], 'add_table')
        eq_(diffs[0][1].name, "parent")
        eq_(diffs[1][0], 'add_table')
        eq_(diffs[1][1].name, "child")

class AutogenRenderTest(TestCase):
    """test individual directives"""

    @classmethod
    @requires_07
    def setup_class(cls):
        cls.autogen_context = {
            'opts': {
                'sqlalchemy_module_prefix': 'sa.',
                'alembic_module_prefix': 'op.',
            },
            'dialect': mysql.dialect()
        }

    def test_render_add_index(self):
        """
        autogenerate._add_index
        """
        m = MetaData()
        t = Table('test', m,
            Column('id', Integer, primary_key=True),
            Column('active', Boolean()),
            Column('code', String(255)),
        )
        idx = Index('test_active_code_idx', t.c.active, t.c.code)
        eq_ignore_whitespace(
            autogenerate._add_index(idx, self.autogen_context),
            "op.create_index('test_active_code_idx', 'test', "
            "['active', 'code'], unique=False)"
        )

    def test_render_add_index_schema(self):
        """
        autogenerate._add_index using schema
        """
        m = MetaData()
        t = Table('test', m,
            Column('id', Integer, primary_key=True),
            Column('active', Boolean()),
            Column('code', String(255)),
            schema='CamelSchema'
        )
        idx = Index('test_active_code_idx', t.c.active, t.c.code)
        eq_ignore_whitespace(
            autogenerate._add_index(idx, self.autogen_context),
            "op.create_index('test_active_code_idx', 'CamelSchema.test', "
            "['active', 'code'], unique=False, schema='CamelSchema')"
        )

    # def test_render_add_index_func(self):
    #     """
    #     autogenerate._drop_index using func -- TODO: SQLA needs to 
    #     reflect expressions as well as columns
    #     """
    #     m = MetaData()
    #     t = Table('test', m,
    #         Column('id', Integer, primary_key=True),
    #         Column('active', Boolean()),
    #         Column('code', String(255)),
    #     )
    #     idx = Index('test_active_lower_code_idx', t.c.active, func.lower(t.c.code))
    #     eq_ignore_whitespace(
    #         autogenerate._add_index(idx, self.autogen_context),
    #         ""
    #     )

    def test_drop_index(self):
        """
        autogenerate._drop_index
        """
        m = MetaData()
        t = Table('test', m,
            Column('id', Integer, primary_key=True),
            Column('active', Boolean()),
            Column('code', String(255)),
        )
        idx = Index('test_active_code_idx', t.c.active, t.c.code)
        eq_ignore_whitespace(
            autogenerate._drop_index(idx, self.autogen_context),
            "op.drop_index('test_active_code_idx', 'test')"
        )

    def test_add_unique_constraint(self):
        """
        autogenerate._add_unique_constraint
        """
        m = MetaData()
        t = Table('test', m,
            Column('id', Integer, primary_key=True),
            Column('active', Boolean()),
            Column('code', String(255)),
        )
        uq = UniqueConstraint(t.c.code, name='uq_test_code')
        eq_ignore_whitespace(
            autogenerate._add_unique_constraint(uq, self.autogen_context),
            "op.create_unique_constraint('uq_test_code', 'test', ['code'])"
        )

    def test_drop_constraint(self):
        """
        autogenerate._drop_constraint
        """
        m = MetaData()
        t = Table('test', m,
            Column('id', Integer, primary_key=True),
            Column('active', Boolean()),
            Column('code', String(255)),
        )
        uq = UniqueConstraint(t.c.code, name='uq_test_code')
        eq_ignore_whitespace(
            autogenerate._drop_constraint(uq, self.autogen_context),
            "op.drop_constraint('uq_test_code', 'test')"
        )

    def test_render_table_upgrade(self):
        m = MetaData()
        t = Table('test', m,
            Column('id', Integer, primary_key=True),
            Column('name', Unicode(255)),
            Column("address_id", Integer, ForeignKey("address.id")),
            Column("timestamp", DATETIME, server_default="NOW()"),
            Column("amount", Numeric(5, 2)),
            UniqueConstraint("name", name="uq_name"),
            UniqueConstraint("timestamp"),
        )
        eq_ignore_whitespace(
            autogenerate._add_table(t, self.autogen_context),
            "op.create_table('test',"
            "sa.Column('id', sa.Integer(), nullable=False),"
            "sa.Column('name', sa.Unicode(length=255), nullable=True),"
            "sa.Column('address_id', sa.Integer(), nullable=True),"
            "sa.Column('timestamp', sa.DATETIME(), "
                "server_default='NOW()', "
                "nullable=True),"
            "sa.Column('amount', sa.Numeric(precision=5, scale=2), nullable=True),"
            "sa.ForeignKeyConstraint(['address_id'], ['address.id'], ),"
            "sa.PrimaryKeyConstraint('id'),"
            "sa.UniqueConstraint('name', name='uq_name'),"
            "sa.UniqueConstraint('timestamp')"
            ")"
        )

    def test_render_table_w_schema(self):
        m = MetaData()
        t = Table('test', m,
            Column('id', Integer, primary_key=True),
            Column('q', Integer, ForeignKey('address.id')),
            schema='foo'
        )
        eq_ignore_whitespace(
            autogenerate._add_table(t, self.autogen_context),
            "op.create_table('test',"
            "sa.Column('id', sa.Integer(), nullable=False),"
            "sa.Column('q', sa.Integer(), nullable=True),"
            "sa.ForeignKeyConstraint(['q'], ['address.id'], ),"
            "sa.PrimaryKeyConstraint('id'),"
            "schema='foo'"
            ")"
        )

    def test_render_table_w_fk_schema(self):
        m = MetaData()
        t = Table('test', m,
            Column('id', Integer, primary_key=True),
            Column('q', Integer, ForeignKey('foo.address.id')),
        )
        eq_ignore_whitespace(
            autogenerate._add_table(t, self.autogen_context),
            "op.create_table('test',"
            "sa.Column('id', sa.Integer(), nullable=False),"
            "sa.Column('q', sa.Integer(), nullable=True),"
            "sa.ForeignKeyConstraint(['q'], ['foo.address.id'], ),"
            "sa.PrimaryKeyConstraint('id')"
            ")"
        )

    def test_render_table_w_metadata_schema(self):
        m = MetaData(schema="foo")
        t = Table('test', m,
            Column('id', Integer, primary_key=True),
            Column('q', Integer, ForeignKey('address.id')),
        )
        eq_ignore_whitespace(
            re.sub(r"u'", "'", autogenerate._add_table(t, self.autogen_context)),
            "op.create_table('test',"
            "sa.Column('id', sa.Integer(), nullable=False),"
            "sa.Column('q', sa.Integer(), nullable=True),"
            "sa.ForeignKeyConstraint(['q'], ['foo.address.id'], ),"
            "sa.PrimaryKeyConstraint('id'),"
            "schema='foo'"
            ")"
        )

    def test_render_table_w_metadata_schema_override(self):
        m = MetaData(schema="foo")
        t = Table('test', m,
            Column('id', Integer, primary_key=True),
            Column('q', Integer, ForeignKey('bar.address.id')),
        )
        eq_ignore_whitespace(
            autogenerate._add_table(t, self.autogen_context),
            "op.create_table('test',"
            "sa.Column('id', sa.Integer(), nullable=False),"
            "sa.Column('q', sa.Integer(), nullable=True),"
            "sa.ForeignKeyConstraint(['q'], ['bar.address.id'], ),"
            "sa.PrimaryKeyConstraint('id'),"
            "schema='foo'"
            ")"
        )

    def test_render_addtl_args(self):
        m = MetaData()
        t = Table('test', m,
            Column('id', Integer, primary_key=True),
            Column('q', Integer, ForeignKey('bar.address.id')),
            postgresql_arg1="some_arg", mysql_engine="InnoDB"
        )
        eq_ignore_whitespace(
            autogenerate._add_table(t, self.autogen_context),
            "op.create_table('test',"
            "sa.Column('id', sa.Integer(), nullable=False),"
            "sa.Column('q', sa.Integer(), nullable=True),"
            "sa.ForeignKeyConstraint(['q'], ['bar.address.id'], ),"
            "sa.PrimaryKeyConstraint('id'),"
            "mysql_engine='InnoDB',postgresql_arg1='some_arg')"
        )

    def test_render_drop_table(self):
        eq_(
            autogenerate._drop_table(Table("sometable", MetaData()),
                        self.autogen_context),
            "op.drop_table('sometable')"
        )

    def test_render_drop_table_w_schema(self):
        eq_(
            autogenerate._drop_table(
                Table("sometable", MetaData(), schema='foo'),
                self.autogen_context),
            "op.drop_table('sometable', schema='foo')"
        )

    def test_render_add_column(self):
        eq_(
            autogenerate._add_column(
                    None, "foo", Column("x", Integer, server_default="5"),
                        self.autogen_context),
            "op.add_column('foo', sa.Column('x', sa.Integer(), "
                "server_default='5', nullable=True))"
        )

    def test_render_add_column_w_schema(self):
        eq_(
            autogenerate._add_column(
                    "foo", "bar", Column("x", Integer, server_default="5"),
                        self.autogen_context),
            "op.add_column('bar', sa.Column('x', sa.Integer(), "
                "server_default='5', nullable=True), schema='foo')"
        )

    def test_render_drop_column(self):
        eq_(
            autogenerate._drop_column(
                    None, "foo", Column("x", Integer, server_default="5"),
                        self.autogen_context),

            "op.drop_column('foo', 'x')"
        )

    def test_render_drop_column_w_schema(self):
        eq_(
            autogenerate._drop_column(
                    "foo", "bar", Column("x", Integer, server_default="5"),
                        self.autogen_context),

            "op.drop_column('bar', 'x', schema='foo')"
        )

    def test_render_quoted_server_default(self):
        eq_(
            autogenerate._render_server_default(
                "nextval('group_to_perm_group_to_perm_id_seq'::regclass)",
                    self.autogen_context),
            '"nextval(\'group_to_perm_group_to_perm_id_seq\'::regclass)"'
        )

    def test_render_col_with_server_default(self):
        c = Column('updated_at', TIMESTAMP(),
                server_default='TIMEZONE("utc", CURRENT_TIMESTAMP)',
                nullable=False)
        result = autogenerate._render_column(
                    c, self.autogen_context
                )
        eq_(
            result,
            'sa.Column(\'updated_at\', sa.TIMESTAMP(), '
                'server_default=\'TIMEZONE("utc", CURRENT_TIMESTAMP)\', '
                'nullable=False)'
        )

    def test_render_col_autoinc_false_mysql(self):
        c = Column('some_key', Integer, primary_key=True, autoincrement=False)
        Table('some_table', MetaData(), c)
        result = autogenerate._render_column(
                    c, self.autogen_context
                )
        eq_(
            result,
            'sa.Column(\'some_key\', sa.Integer(), '
                'autoincrement=False, '
                'nullable=False)'
        )

    def test_render_custom(self):

        def render(type_, obj, context):
            if type_ == "foreign_key":
                return None
            if type_ == "column":
                if obj.name == "y":
                    return None
                else:
                    return "col(%s)" % obj.name
            return "render:%s" % type_

        autogen_context = {"opts": {
            'render_item': render,
            'alembic_module_prefix': 'sa.'
        }}

        t = Table('t', MetaData(),
                Column('x', Integer),
                Column('y', Integer),
                PrimaryKeyConstraint('x'),
                ForeignKeyConstraint(['x'], ['y'])
            )
        result = autogenerate._add_table(
                    t, autogen_context
                )
        eq_(
            result, """sa.create_table('t',
col(x),
render:primary_key\n)"""
        )

    def test_render_modify_type(self):
        eq_ignore_whitespace(
            autogenerate._modify_col(
                        "sometable", "somecolumn",
                        self.autogen_context,
                        type_=CHAR(10), existing_type=CHAR(20)),
            "op.alter_column('sometable', 'somecolumn', "
                "existing_type=sa.CHAR(length=20), type_=sa.CHAR(length=10))"
        )

    def test_render_modify_type_w_schema(self):
        eq_ignore_whitespace(
            autogenerate._modify_col(
                        "sometable", "somecolumn",
                        self.autogen_context,
                        type_=CHAR(10), existing_type=CHAR(20),
                        schema='foo'),
            "op.alter_column('sometable', 'somecolumn', "
                "existing_type=sa.CHAR(length=20), type_=sa.CHAR(length=10), "
                "schema='foo')"
        )

    def test_render_modify_nullable(self):
        eq_ignore_whitespace(
            autogenerate._modify_col(
                        "sometable", "somecolumn",
                        self.autogen_context,
                        existing_type=Integer(),
                        nullable=True),
            "op.alter_column('sometable', 'somecolumn', "
            "existing_type=sa.Integer(), nullable=True)"
        )

    def test_render_modify_nullable_w_schema(self):
        eq_ignore_whitespace(
            autogenerate._modify_col(
                        "sometable", "somecolumn",
                        self.autogen_context,
                        existing_type=Integer(),
                        nullable=True, schema='foo'),
            "op.alter_column('sometable', 'somecolumn', "
            "existing_type=sa.Integer(), nullable=True, schema='foo')"
        )

    def test_render_fk_constraint_kwarg(self):
        m = MetaData()
        t1 = Table('t', m, Column('c', Integer))
        t2 = Table('t2', m, Column('c_rem', Integer))

        fk = ForeignKeyConstraint([t1.c.c], [t2.c.c_rem], onupdate="CASCADE")
        if not util.sqla_08:
            t1.append_constraint(fk)

        eq_ignore_whitespace(
            re.sub(r"u'", "'", autogenerate._render_constraint(fk, self.autogen_context)),
            "sa.ForeignKeyConstraint(['c'], ['t2.c_rem'], onupdate='CASCADE')"
        )

        fk = ForeignKeyConstraint([t1.c.c], [t2.c.c_rem], ondelete="CASCADE")
        if not util.sqla_08:
            t1.append_constraint(fk)

        eq_ignore_whitespace(
            re.sub(r"u'", "'", autogenerate._render_constraint(fk, self.autogen_context)),
            "sa.ForeignKeyConstraint(['c'], ['t2.c_rem'], ondelete='CASCADE')"
        )

        fk = ForeignKeyConstraint([t1.c.c], [t2.c.c_rem], deferrable=True)
        if not util.sqla_08:
            t1.append_constraint(fk)
        eq_ignore_whitespace(
            re.sub(r"u'", "'", autogenerate._render_constraint(fk, self.autogen_context)),
            "sa.ForeignKeyConstraint(['c'], ['t2.c_rem'], deferrable=True)"
        )

        fk = ForeignKeyConstraint([t1.c.c], [t2.c.c_rem], initially="XYZ")
        if not util.sqla_08:
            t1.append_constraint(fk)
        eq_ignore_whitespace(
            re.sub(r"u'", "'", autogenerate._render_constraint(fk, self.autogen_context)),
            "sa.ForeignKeyConstraint(['c'], ['t2.c_rem'], initially='XYZ')"
        )

    def test_render_fk_constraint_use_alter(self):
        m = MetaData()
        Table('t', m, Column('c', Integer))
        t2 = Table('t2', m, Column('c_rem', Integer,
                                ForeignKey('t.c', name="fk1", use_alter=True)))
        const = list(t2.foreign_keys)[0].constraint

        eq_ignore_whitespace(
            autogenerate._render_constraint(const, self.autogen_context),
            "sa.ForeignKeyConstraint(['c_rem'], ['t.c'], "
                    "name='fk1', use_alter=True)"
        )

    def test_render_check_constraint_literal(self):
        eq_ignore_whitespace(
            autogenerate._render_check_constraint(
                CheckConstraint("im a constraint", name='cc1'),
                self.autogen_context
            ),
            "sa.CheckConstraint('im a constraint', name='cc1')"
        )

    def test_render_check_constraint_sqlexpr(self):
        c = column('c')
        five = literal_column('5')
        ten = literal_column('10')
        eq_ignore_whitespace(
            autogenerate._render_check_constraint(
                CheckConstraint(and_(c > five, c < ten)),
                self.autogen_context
            ),
            "sa.CheckConstraint('c > 5 AND c < 10')"
        )

    def test_render_modify_nullable_w_default(self):
        eq_ignore_whitespace(
            autogenerate._modify_col(
                        "sometable", "somecolumn",
                        self.autogen_context,
                        existing_type=Integer(),
                        existing_server_default="5",
                        nullable=True),
            "op.alter_column('sometable', 'somecolumn', "
            "existing_type=sa.Integer(), nullable=True, "
            "existing_server_default='5')"
        )

    def test_render_enum(self):
        eq_ignore_whitespace(
            autogenerate._repr_type(
                        "sa.",
                        Enum("one", "two", "three", name="myenum"),
                        self.autogen_context),
            "sa.Enum('one', 'two', 'three', name='myenum')"
        )
        eq_ignore_whitespace(
            autogenerate._repr_type(
                        "sa.",
                        Enum("one", "two", "three"),
                        self.autogen_context),
            "sa.Enum('one', 'two', 'three')"
        )

# TODO: tests for dialect-specific type rendering + imports
