
from sqlalchemy import DateTime, MetaData, Table, Column, text, Integer, \
    String, Interval, Sequence, Numeric, BigInteger, Float, Numeric
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.engine.reflection import Inspector
from alembic.operations import Operations
from sqlalchemy.sql import table, column
from alembic.autogenerate.compare import \
    _compare_server_default, _compare_tables, _render_server_default_for_compare

from alembic.operations import ops
from alembic import command, util
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.autogenerate import api

from alembic.testing import eq_, provide_metadata
from alembic.testing.env import staging_env, clear_staging_env, \
    _no_sql_testing_config, write_script
from alembic.testing.fixtures import capture_context_buffer
from alembic.testing.fixtures import TestBase
from alembic.testing.fixtures import op_fixture
from alembic.testing import config
from alembic import op


class PostgresqlOpTest(TestBase):

    def test_rename_table_postgresql(self):
        context = op_fixture("postgresql")
        op.rename_table('t1', 't2')
        context.assert_("ALTER TABLE t1 RENAME TO t2")

    def test_rename_table_schema_postgresql(self):
        context = op_fixture("postgresql")
        op.rename_table('t1', 't2', schema="foo")
        context.assert_("ALTER TABLE foo.t1 RENAME TO t2")

    @config.requirements.fail_before_sqla_080
    def test_create_index_postgresql_expressions(self):
        context = op_fixture("postgresql")
        op.create_index(
            'geocoded',
            'locations',
            [text('lower(coordinates)')],
            postgresql_where=text("locations.coordinates != Null"))
        context.assert_(
            "CREATE INDEX geocoded ON locations (lower(coordinates)) "
            "WHERE locations.coordinates != Null")

    def test_create_index_postgresql_where(self):
        context = op_fixture("postgresql")
        op.create_index(
            'geocoded',
            'locations',
            ['coordinates'],
            postgresql_where=text("locations.coordinates != Null"))
        context.assert_(
            "CREATE INDEX geocoded ON locations (coordinates) "
            "WHERE locations.coordinates != Null")

    def test_alter_column_type_using(self):
        context = op_fixture('postgresql')
        op.alter_column("t", "c", type_=Integer, postgresql_using='c::integer')
        context.assert_(
            'ALTER TABLE t ALTER COLUMN c TYPE INTEGER USING c::integer'
        )


class PGOfflineEnumTest(TestBase):

    def setUp(self):
        staging_env()
        self.cfg = cfg = _no_sql_testing_config()

        self.rid = rid = util.rev_id()

        self.script = script = ScriptDirectory.from_config(cfg)
        script.generate_revision(rid, None, refresh=True)

    def tearDown(self):
        clear_staging_env()

    def _inline_enum_script(self):
        write_script(self.script, self.rid, """
revision = '%s'
down_revision = None

from alembic import op
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy import Column


def upgrade():
    op.create_table("sometable",
        Column("data", ENUM("one", "two", "three", name="pgenum"))
    )


def downgrade():
    op.drop_table("sometable")
""" % self.rid)

    def _distinct_enum_script(self):
        write_script(self.script, self.rid, """
revision = '%s'
down_revision = None

from alembic import op
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy import Column


def upgrade():
    enum = ENUM("one", "two", "three", name="pgenum", create_type=False)
    enum.create(op.get_bind(), checkfirst=False)
    op.create_table("sometable",
        Column("data", enum)
    )


def downgrade():
    op.drop_table("sometable")
    ENUM(name="pgenum").drop(op.get_bind(), checkfirst=False)

""" % self.rid)

    @config.requirements.sqlalchemy_09
    def test_offline_inline_enum_create(self):
        self._inline_enum_script()
        with capture_context_buffer() as buf:
            command.upgrade(self.cfg, self.rid, sql=True)
        assert "CREATE TYPE pgenum AS "\
            "ENUM ('one', 'two', 'three')" in buf.getvalue()
        assert "CREATE TABLE sometable (\n    data pgenum\n)" in buf.getvalue()

    def test_offline_inline_enum_drop(self):
        self._inline_enum_script()
        with capture_context_buffer() as buf:
            command.downgrade(self.cfg, "%s:base" % self.rid, sql=True)
        assert "DROP TABLE sometable" in buf.getvalue()
        # no drop since we didn't emit events
        assert "DROP TYPE pgenum" not in buf.getvalue()

    @config.requirements.sqlalchemy_09
    def test_offline_distinct_enum_create(self):
        self._distinct_enum_script()
        with capture_context_buffer() as buf:
            command.upgrade(self.cfg, self.rid, sql=True)
        assert "CREATE TYPE pgenum AS ENUM "\
            "('one', 'two', 'three')" in buf.getvalue()
        assert "CREATE TABLE sometable (\n    data pgenum\n)" in buf.getvalue()

    def test_offline_distinct_enum_drop(self):
        self._distinct_enum_script()
        with capture_context_buffer() as buf:
            command.downgrade(self.cfg, "%s:base" % self.rid, sql=True)
        assert "DROP TABLE sometable" in buf.getvalue()
        assert "DROP TYPE pgenum" in buf.getvalue()


class PostgresqlInlineLiteralTest(TestBase):
    __only_on__ = 'postgresql'

    @classmethod
    def setup_class(cls):
        cls.bind = config.db
        cls.bind.execute("""
            create table tab (
                col varchar(50)
            )
        """)
        cls.bind.execute("""
            insert into tab (col) values
                ('old data 1'),
                ('old data 2.1'),
                ('old data 3')
        """)

    @classmethod
    def teardown_class(cls):
        cls.bind.execute("drop table tab")

    def setUp(self):
        self.conn = self.bind.connect()
        ctx = MigrationContext.configure(self.conn)
        self.op = Operations(ctx)

    def tearDown(self):
        self.conn.close()

    def test_inline_percent(self):
        # TODO: here's the issue, you need to escape this.
        tab = table('tab', column('col'))
        self.op.execute(
            tab.update().where(
                tab.c.col.like(self.op.inline_literal('%.%'))
            ).values(col=self.op.inline_literal('new data')),
            execution_options={'no_parameters': True}
        )
        eq_(
            self.conn.execute(
                "select count(*) from tab where col='new data'").scalar(),
            1,
        )


class PostgresqlDefaultCompareTest(TestBase):
    __only_on__ = 'postgresql'

    @classmethod
    def setup_class(cls):
        cls.bind = config.db
        staging_env()
        cls.migration_context = MigrationContext.configure(
            connection=cls.bind.connect(),
            opts={
                'compare_type': True,
                'compare_server_default': True
            }
        )

    def setUp(self):
        self.metadata = MetaData(self.bind)
        self.autogen_context = api.AutogenContext(self.migration_context)

    @classmethod
    def teardown_class(cls):
        clear_staging_env()

    def tearDown(self):
        self.metadata.drop_all()

    def _compare_default_roundtrip(
            self, type_, orig_default, alternate=None, diff_expected=None):
        diff_expected = diff_expected \
            if diff_expected is not None \
            else alternate is not None
        if alternate is None:
            alternate = orig_default

        t1 = Table("test", self.metadata,
                   Column("somecol", type_, server_default=orig_default))
        t2 = Table("test", MetaData(),
                   Column("somecol", type_, server_default=alternate))

        t1.create(self.bind)

        insp = Inspector.from_engine(self.bind)
        cols = insp.get_columns(t1.name)
        insp_col = Column("somecol", cols[0]['type'],
                          server_default=text(cols[0]['default']))
        op = ops.AlterColumnOp("test", "somecol")
        _compare_server_default(
            self.autogen_context, op,
            None, "test", "somecol", insp_col, t2.c.somecol)

        diffs = op.to_diff_tuple()
        eq_(bool(diffs), diff_expected)

    def _compare_default(
        self,
        t1, t2, col,
        rendered
    ):
        t1.create(self.bind, checkfirst=True)
        insp = Inspector.from_engine(self.bind)
        cols = insp.get_columns(t1.name)
        ctx = self.autogen_context.migration_context

        return ctx.impl.compare_server_default(
            None,
            col,
            rendered,
            cols[0]['default'])

    def test_compare_interval_str(self):
        # this form shouldn't be used but testing here
        # for compatibility
        self._compare_default_roundtrip(
            Interval,
            "14 days"
        )

    @config.requirements.postgresql_uuid_ossp
    def test_compare_uuid_text(self):
        self._compare_default_roundtrip(
            UUID,
            text("uuid_generate_v4()")
        )

    def test_compare_interval_text(self):
        self._compare_default_roundtrip(
            Interval,
            text("'14 days'")
        )

    def test_compare_array_of_integer_text(self):
        self._compare_default_roundtrip(
            ARRAY(Integer),
            text("(ARRAY[]::integer[])")
        )

    def test_compare_current_timestamp_text(self):
        self._compare_default_roundtrip(
            DateTime(),
            text("TIMEZONE('utc', CURRENT_TIMESTAMP)"),
        )

    def test_compare_integer_str(self):
        self._compare_default_roundtrip(
            Integer(),
            "5",
        )

    def test_compare_integer_text(self):
        self._compare_default_roundtrip(
            Integer(),
            text("5"),
        )

    def test_compare_integer_text_diff(self):
        self._compare_default_roundtrip(
            Integer(),
            text("5"), "7"
        )

    def test_compare_float_str(self):
        self._compare_default_roundtrip(
            Float(),
            "5.2",
        )

    def test_compare_float_text(self):
        self._compare_default_roundtrip(
            Float(),
            text("5.2"),
        )

    def test_compare_float_no_diff1(self):
        self._compare_default_roundtrip(
            Float(),
            text("5.2"), "5.2",
            diff_expected=False
        )

    def test_compare_float_no_diff2(self):
        self._compare_default_roundtrip(
            Float(),
            "5.2", text("5.2"),
            diff_expected=False
        )

    def test_compare_float_no_diff3(self):
        self._compare_default_roundtrip(
            Float(),
            text("5"), text("5.0"),
            diff_expected=False
        )

    def test_compare_float_no_diff4(self):
        self._compare_default_roundtrip(
            Float(),
            "5", "5.0",
            diff_expected=False
        )

    def test_compare_float_no_diff5(self):
        self._compare_default_roundtrip(
            Float(),
            text("5"), "5.0",
            diff_expected=False
        )

    def test_compare_float_no_diff6(self):
        self._compare_default_roundtrip(
            Float(),
            "5", text("5.0"),
            diff_expected=False
        )

    def test_compare_numeric_no_diff(self):
        self._compare_default_roundtrip(
            Numeric(),
            text("5"), "5.0",
            diff_expected=False
        )

    def test_compare_unicode_literal(self):
        self._compare_default_roundtrip(
            String(),
            u'im a default'
        )

    # TOOD: will need to actually eval() the repr() and
    # spend more effort figuring out exactly the kind of expression
    # to use
    def _TODO_test_compare_character_str_w_singlequote(self):
        self._compare_default_roundtrip(
            String(),
            "hel''lo",
        )

    def test_compare_character_str(self):
        self._compare_default_roundtrip(
            String(),
            "hello",
        )

    def test_compare_character_text(self):
        self._compare_default_roundtrip(
            String(),
            text("'hello'"),
        )

    def test_compare_character_str_diff(self):
        self._compare_default_roundtrip(
            String(),
            "hello",
            "there"
        )

    def test_compare_character_text_diff(self):
        self._compare_default_roundtrip(
            String(),
            text("'hello'"),
            text("'there'")
        )

    def test_primary_key_skip(self):
        """Test that SERIAL cols are just skipped"""
        t1 = Table("sometable", self.metadata,
                   Column("id", Integer, primary_key=True)
                   )
        t2 = Table("sometable", MetaData(),
                   Column("id", Integer, primary_key=True)
                   )
        assert not self._compare_default(
            t1, t2, t2.c.id, ""
        )


class PostgresqlDetectSerialTest(TestBase):
    __only_on__ = 'postgresql'

    @classmethod
    def setup_class(cls):
        cls.bind = config.db
        cls.conn = cls.bind.connect()
        staging_env()
        cls.migration_context = MigrationContext.configure(
            connection=cls.conn,
            opts={
                'compare_type': True,
                'compare_server_default': True
            }
        )

    def setUp(self):
        self.autogen_context = api.AutogenContext(self.migration_context)

    @classmethod
    def teardown_class(cls):
        cls.conn.close()
        clear_staging_env()

    @provide_metadata
    def _expect_default(self, c_expected, col, seq=None):
        Table('t', self.metadata, col)

        if seq:
            seq._set_metadata(self.metadata)
        self.metadata.create_all(config.db)

        insp = Inspector.from_engine(config.db)

        uo = ops.UpgradeOps(ops=[])
        _compare_tables(
            set([(None, 't')]), set([]),
            insp, self.metadata, uo, self.autogen_context)
        diffs = uo.as_diffs()
        tab = diffs[0][1]

        eq_(_render_server_default_for_compare(
            tab.c.x.server_default, tab.c.x, self.autogen_context),
            c_expected)

        insp = Inspector.from_engine(config.db)
        uo = ops.UpgradeOps(ops=[])
        m2 = MetaData()
        Table('t', m2, Column('x', BigInteger()))
        _compare_tables(
            set([(None, 't')]), set([(None, 't')]),
            insp, m2, uo, self.autogen_context)
        diffs = uo.as_diffs()
        server_default = diffs[0][0][4]['existing_server_default']
        eq_(_render_server_default_for_compare(
            server_default, tab.c.x, self.autogen_context),
            c_expected)

    def test_serial(self):
        self._expect_default(
            None,
            Column('x', Integer, primary_key=True)
        )

    def test_separate_seq(self):
        seq = Sequence("x_id_seq")
        self._expect_default(
            "nextval('x_id_seq'::regclass)",
            Column(
                'x', Integer,
                server_default=seq.next_value(), primary_key=True),
            seq
        )

    def test_numeric(self):
        seq = Sequence("x_id_seq")
        self._expect_default(
            "nextval('x_id_seq'::regclass)",
            Column(
                'x', Numeric(8, 2), server_default=seq.next_value(),
                primary_key=True),
            seq
        )

    def test_no_default(self):
        self._expect_default(
            None,
            Column('x', Integer, autoincrement=False, primary_key=True)
        )
