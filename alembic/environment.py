import alembic
from alembic.operations import Operations
from alembic.migration import MigrationContext
from alembic import util
from sqlalchemy.engine import url as sqla_url

class EnvironmentContext(object):
    """Represent the state made available to an env.py script."""

    _migration_context = None

    def __init__(self, config, script, **kw):
        self.config = config
        self.script = script
        self.context_opts = kw

    def __enter__(self):
        """Establish a context which provides a 
        :class:`.EnvironmentContext` object to
        env.py scripts.
    
        The :class:`.EnvironmentContext` will
        be made available as ``from alembic import context``.
    
        """
        alembic.context = self
        return self

    def __exit__(self, *arg, **kw):
        del alembic.context
        alembic.op._proxy = None

    def is_offline_mode(self):
        """Return True if the current migrations environment 
        is running in "offline mode".

        This is ``True`` or ``False`` depending 
        on the the ``--sql`` flag passed.

        This function does not require that the :class:`.MigrationContext` 
        has been configured.

        """
        return self.context_opts.get('as_sql', False)

    def is_transactional_ddl(self):
        """Return True if the context is configured to expect a
        transactional DDL capable backend.

        This defaults to the type of database in use, and 
        can be overridden by the ``transactional_ddl`` argument
        to :meth:`.configure`

        This function requires that a :class:`.MigrationContext` has first been 
        made available via :meth:`.configure`.

        """
        return self.migration_context.impl.transactional_ddl

    def requires_connection(self):
        return not self.is_offline_mode()

    def get_head_revision(self):
        """Return the hex identifier of the 'head' revision.

        This function does not require that the :class:`.MigrationContext` 
        has been configured.

        """
        return self.script._as_rev_number("head")

    def get_starting_revision_argument(self):
        """Return the 'starting revision' argument,
        if the revision was passed using ``start:end``.

        This is only meaningful in "offline" mode.
        Returns ``None`` if no value is available
        or was configured.

        This function does not require that the :class:`.MigrationContext` 
        has been configured.

        """
        if self._migration_context is not None:
            return self.script._as_rev_number(self.migration_context._start_from_rev)
        elif 'starting_rev' in self.context_opts:
            return self.script._as_rev_number(self.context_opts['starting_rev'])
        else:
            raise util.CommandError("No starting revision argument is available.")

    def get_revision_argument(self):
        """Get the 'destination' revision argument.

        This is typically the argument passed to the 
        ``upgrade`` or ``downgrade`` command.

        If it was specified as ``head``, the actual 
        version number is returned; if specified
        as ``base``, ``None`` is returned.

        This function does not require that the :class:`.MigrationContext` 
        has been configured.

        """
        return self.script._as_rev_number(self.context_opts['destination_rev'])

    def get_tag_argument(self):
        """Return the value passed for the ``--tag`` argument, if any.

        The ``--tag`` argument is not used directly by Alembic,
        but is available for custom ``env.py`` configurations that 
        wish to use it; particularly for offline generation scripts
        that wish to generate tagged filenames.

        This function does not require that the :class:`.MigrationContext` 
        has been configured.

        """
        return self.context_opts.get('tag', None)

    def configure(self,
            connection=None,
            url=None,
            dialect_name=None,
            transactional_ddl=None,
            output_buffer=None,
            starting_rev=None,
            tag=None,
            target_metadata=None,
            compare_type=False,
            compare_server_default=False,
            upgrade_token="upgrades",
            downgrade_token="downgrades",
            alembic_module_prefix="op.",
            sqlalchemy_module_prefix="sa.",
            **kw
        ):
        """Configure the migration environment.

        The important thing needed here is first a way to figure out
        what kind of "dialect" is in use.   The second is to pass
        an actual database connection, if one is required.

        If the :func:`.is_offline_mode` function returns ``True``,
        then no connection is needed here.  Otherwise, the
        ``connection`` parameter should be present as an 
        instance of :class:`sqlalchemy.engine.base.Connection`.

        This function is typically called from the ``env.py``
        script within a migration environment.  It can be called
        multiple times for an invocation.  The most recent :class:`~sqlalchemy.engine.base.Connection`
        for which it was called is the one that will be operated upon
        by the next call to :func:`.run_migrations`.

        General parameters:
    
        :param connection: a :class:`~sqlalchemy.engine.base.Connection` to use
         for SQL execution in "online" mode.  When present, is also used to 
         determine the type of dialect in use.
        :param url: a string database url, or a :class:`sqlalchemy.engine.url.URL` object.
         The type of dialect to be used will be derived from this if ``connection`` is
         not passed.
        :param dialect_name: string name of a dialect, such as "postgresql", "mssql", etc.
         The type of dialect to be used will be derived from this if ``connection``
         and ``url`` are not passed.
        :param transactional_ddl: Force the usage of "transactional" DDL on or off;
         this otherwise defaults to whether or not the dialect in use supports it.
        :param output_buffer: a file-like object that will be used for textual output
         when the ``--sql`` option is used to generate SQL scripts.  Defaults to
         ``sys.stdout`` if not passed here and also not present on the :class:`.Config`
         object.  The value here overrides that of the :class:`.Config` object.
        :param starting_rev: Override the "starting revision" argument when using
         ``--sql`` mode.
        :param tag: a string tag for usage by custom ``env.py`` scripts.  Set via
         the ``--tag`` option, can be overridden here.
     
        Parameters specific to the autogenerate feature, when ``alembic revision``
        is run with the ``--autogenerate`` feature:
    
        :param target_metadata: a :class:`sqlalchemy.schema.MetaData` object that
         will be consulted during autogeneration.  The tables present will be compared against
         what is locally available on the target :class:`~sqlalchemy.engine.base.Connection`
         to produce candidate upgrade/downgrade operations.
     
        :param compare_type: Indicates type comparison behavior during an autogenerate
         operation.  Defaults to ``False`` which disables type comparison.  Set to 
         ``True`` to turn on default type comparison, which has varied accuracy depending
         on backend.
     
         To customize type comparison behavior, a callable may be specified which
         can filter type comparisons during an autogenerate operation.   The format of 
         this callable is::
     
            def my_compare_type(context, inspected_column, 
                        metadata_column, inspected_type, metadata_type):
                # return True if the types are different,
                # False if not, or None to allow the default implementation
                # to compare these types
                pass
    
         ``inspected_column`` is a dictionary structure as returned by
         :meth:`sqlalchemy.engine.reflection.Inspector.get_columns`, whereas
         ``metadata_column`` is a :class:`sqlalchemy.schema.Column` from
         the local model environment.
     
         A return value of ``None`` indicates to allow default type comparison to
         proceed.

        :param compare_server_default: Indicates server default comparison behavior during 
         an autogenerate operation.  Defaults to ``False`` which disables server default 
         comparison.  Set to  ``True`` to turn on server default comparison, which has 
         varied accuracy depending on backend.
    
         To customize server default comparison behavior, a callable may be specified
         which can filter server default comparisons during an autogenerate operation.
         defaults during an autogenerate operation.   The format of this callable is::
     
            def my_compare_server_default(context, inspected_column, 
                        metadata_column, inspected_default, metadata_default,
                        rendered_metadata_default):
                # return True if the defaults are different,
                # False if not, or None to allow the default implementation
                # to compare these defaults
                pass

         ``inspected_column`` is a dictionary structure as returned by
         :meth:`sqlalchemy.engine.reflection.Inspector.get_columns`, whereas
         ``metadata_column`` is a :class:`sqlalchemy.schema.Column` from
         the local model environment.

         A return value of ``None`` indicates to allow default server default comparison 
         to proceed.  Note that some backends such as Postgresql actually execute
         the two defaults on the database side to compare for equivalence.

        :param upgrade_token: When autogenerate completes, the text of the 
         candidate upgrade operations will be present in this template 
         variable when ``script.py.mako`` is rendered.  Defaults to ``upgrades``.
        :param downgrade_token: When autogenerate completes, the text of the 
         candidate downgrade operations will be present in this
         template variable when ``script.py.mako`` is rendered.  Defaults to 
         ``downgrades``.

        :param alembic_module_prefix: When autogenerate refers to Alembic 
         :mod:`alembic.op` constructs, this prefix will be used
         (i.e. ``op.create_table``)  Defaults to "``op.``".
         Can be ``None`` to indicate no prefix.  
     
        :param sqlalchemy_module_prefix: When autogenerate refers to SQLAlchemy 
         :class:`~sqlalchemy.schema.Column` or type classes, this prefix will be used
         (i.e. ``sa.Column("somename", sa.Integer)``)  Defaults to "``sa.``".
         Can be ``None`` to indicate no prefix.  
         Note that when dialect-specific types are rendered, autogenerate
         will render them using the dialect module name, i.e. ``mssql.BIT()``, 
         ``postgresql.UUID()``.
     
        Parameters specific to individual backends:
    
        :param mssql_batch_separator: The "batch separator" which will be placed
         between each statement when generating offline SQL Server 
         migrations.  Defaults to ``GO``.  Note this is in addition to the customary
         semicolon ``;`` at the end of each statement; SQL Server considers
         the "batch separator" to denote the end of an individual statement
         execution, and cannot group certain dependent operations in 
         one step.

        """

        if connection:
            dialect = connection.dialect
        elif url:
            url = sqla_url.make_url(url)
            dialect = url.get_dialect()()
        elif dialect_name:
            url = sqla_url.make_url("%s://" % dialect_name)
            dialect = url.get_dialect()()
        else:
            raise Exception("Connection, url, or dialect_name is required.")

        opts = self.context_opts
        if transactional_ddl is not None:
            opts["transactional_ddl"] =  transactional_ddl
        if output_buffer is not None:
            opts["output_buffer"] = output_buffer
        elif self.config.output_buffer is not None:
            opts["output_buffer"] = self.config.output_buffer
        if starting_rev:
            opts['starting_rev'] = starting_rev
        if tag:
            opts['tag'] = tag
        opts['target_metadata'] = target_metadata
        opts['upgrade_token'] = upgrade_token
        opts['downgrade_token'] = downgrade_token
        opts['sqlalchemy_module_prefix'] = sqlalchemy_module_prefix
        opts['alembic_module_prefix'] = alembic_module_prefix
        opts.update(kw)

        self._migration_context = MigrationContext(
                            dialect, self.script, connection, 
                            opts,
                            as_sql=opts.get('as_sql', False), 
                            output_buffer=opts.get("output_buffer"),
                            transactional_ddl=opts.get("transactional_ddl"),
                            starting_rev=opts.get("starting_rev"),
                            compare_type=compare_type,
                            compare_server_default=compare_server_default,
                        )
        alembic.op._proxy = Operations(self._migration_context)

    def run_migrations(self, **kw):
        """Run migrations as determined by the current command line configuration
        as well as versioning information present (or not) in the current 
        database connection (if one is present).

        The function accepts optional ``**kw`` arguments.   If these are
        passed, they are sent directly to the ``upgrade()`` and ``downgrade()``
        functions within each target revision file.   By modifying the
        ``script.py.mako`` file so that the ``upgrade()`` and ``downgrade()``
        functions accept arguments, parameters can be passed here so that
        contextual information, usually information to identify a particular
        database in use, can be passed from a custom ``env.py`` script
        to the migration functions.

        This function requires that a :class:`.MigrationContext` has first been 
        made available via :func:`.configure`.

        """
        self.migration_context.run_migrations(**kw)

    def execute(self, sql):
        """Execute the given SQL using the current change context.

        The behavior of :func:`.context.execute` is the same
        as that of :func:`.op.execute`.  Please see that
        function's documentation for full detail including
        caveats and limitations.

        This function requires that a :class:`.MigrationContext` has first been 
        made available via :func:`.configure`.

        """
        self.migration_context.execute(sql)

    def static_output(self, text):
        """Emit text directly to the "offline" SQL stream.
    
        Typically this is for emitting comments that 
        start with --.  The statement is not treated
        as a SQL execution, no ; or batch separator
        is added, etc.
    
        """
        self.migration_context.impl.static_output(text)

    def begin_transaction(self):
        """Return a context manager that will 
        enclose an operation within a "transaction",
        as defined by the environment's offline
        and transactional DDL settings.

        e.g.::
    
            with context.begin_transaction():
                context.run_migrations()
    
        :meth:`.begin_transaction` is intended to
        "do the right thing" regardless of 
        calling context:
    
        * If :meth:`.is_transactional_ddl` is ``False``,
          returns a "do nothing" context manager
          which otherwise produces no transactional
          state or directives.
        * If :meth:`.is_offline_mode` is ``True``,
          returns a context manager that will
          invoke the :meth:`.DefaultImpl.emit_begin`
          and :meth:`.DefaultImpl.emit_commit`
          methods, which will produce the string
          directives ``BEGIN`` and ``COMMIT`` on
          the output stream, as rendered by the
          target backend (e.g. SQL Server would
          emit ``BEGIN TRANSACTION``).
        * Otherwise, calls :meth:`sqlalchemy.engine.base.Connection.begin`
          on the current online connection, which
          returns a :class:`sqlalchemy.engine.base.Transaction`
          object.  This object demarcates a real
          transaction and is itself a context manager,
          which will roll back if an exception
          is raised.
    
        Note that a custom ``env.py`` script which 
        has more specific transactional needs can of course
        manipulate the :class:`~sqlalchemy.engine.base.Connection`
        directly to produce transactional state in "online"
        mode.

        """
        if not self.is_transactional_ddl():
            @contextmanager
            def do_nothing():
                yield
            return do_nothing()
        elif self.is_offline_mode():
            @contextmanager
            def begin_commit():
                self.migration_context.impl.emit_begin()
                yield
                self.migration_context.impl.emit_commit()
            return begin_commit()
        else:
            return self.get_bind().begin()

    @property
    def migration_context(self):
        """Return the current :class:`.MigrationContext` object.

        If :meth:`.EnvironmentContext.configure` has not been called yet, raises
        an exception.

        Generally, env.py scripts should access the module-level functions
        in :mod:`alebmic.context` to get at this object's functionality.

        """
        if self._migration_context is None:
            raise Exception("No context has been configured yet.")
        return self._migration_context

    def get_context(self):
        """A synonym for :attr:`.EnvironmentContext.migration_context`."""

        return self.migration_context

    def get_bind(self):
        """Return the current 'bind'.

        In "online" mode, this is the 
        :class:`sqlalchemy.engine.Connection` currently being used
        to emit SQL to the database.

        This function requires that a :class:`.MigrationContext` has first been 
        made available via :meth:`.configure`.

        """
        return self.migration_context.bind

    def get_impl(self):
        return self.migration_context.impl

configure = EnvironmentContext