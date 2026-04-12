"""add property scoped room types

Revision ID: c6f1a2d9e411
Revises: b7c4f1d92e11
Create Date: 2026-04-12 16:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c6f1a2d9e411'
down_revision = 'b7c4f1d92e11'
branch_labels = None
depends_on = None


def _backfill_room_types():
    bind = op.get_bind()
    metadata = sa.MetaData()

    categories = sa.Table('categories', metadata, autoload_with=bind)
    rooms = sa.Table('rooms', metadata, autoload_with=bind)
    rate_plans = sa.Table('rate_plans', metadata, autoload_with=bind)
    room_online = sa.Table('room_online', metadata, autoload_with=bind)
    bookings = sa.Table('bookings', metadata, autoload_with=bind)
    channel_room_maps = sa.Table('channel_room_maps', metadata, autoload_with=bind)
    room_types = sa.Table('room_types', metadata, autoload_with=bind)

    category_rows = bind.execute(
        sa.select(
            categories.c.id,
            categories.c.name,
            categories.c.capacity,
            categories.c.description,
        )
    ).fetchall()
    category_lookup = {
        row.id: {
            'name': row.name,
            'capacity': row.capacity or 1,
            'description': row.description or '',
        }
        for row in category_rows
    }

    property_category_pairs = set()
    for row in bind.execute(
        sa.select(rooms.c.property_id, rooms.c.category_id).where(rooms.c.category_id.isnot(None))
    ):
        property_category_pairs.add((row.property_id, row.category_id))
    for row in bind.execute(
        sa.select(rate_plans.c.property_id, rate_plans.c.category_id).where(rate_plans.c.category_id.isnot(None))
    ):
        property_category_pairs.add((row.property_id, row.category_id))
    for row in bind.execute(
        sa.select(room_online.c.property_id, room_online.c.category_id).where(room_online.c.category_id.isnot(None))
    ):
        property_category_pairs.add((row.property_id, row.category_id))

    room_type_map = {}
    used_names = {}
    for property_id, category_id in sorted(property_category_pairs):
        category_data = category_lookup.get(category_id, {})
        base_name = category_data.get('name') or f'Room Type {category_id}'
        property_used_names = used_names.setdefault(property_id, set())
        candidate_name = base_name
        if candidate_name in property_used_names:
            candidate_name = f'{base_name} #{category_id}'
        property_used_names.add(candidate_name)
        insert_result = bind.execute(
            room_types.insert().values(
                property_id=property_id,
                name=candidate_name,
                description=category_data.get('description') or '',
                max_guests=category_data.get('capacity') or 1,
                max_adults=category_data.get('capacity') or 1,
                max_children=0,
                max_infants=0,
                is_active=True,
            )
        )
        room_type_id = insert_result.inserted_primary_key[0]
        room_type_map[(property_id, category_id)] = room_type_id

    for (property_id, category_id), room_type_id in room_type_map.items():
        bind.execute(
            rooms.update()
            .where(
                sa.and_(
                    rooms.c.property_id == property_id,
                    rooms.c.category_id == category_id,
                )
            )
            .values(room_type_id=room_type_id)
        )
        bind.execute(
            rate_plans.update()
            .where(
                sa.and_(
                    rate_plans.c.property_id == property_id,
                    rate_plans.c.category_id == category_id,
                )
            )
            .values(room_type_id=room_type_id)
        )
        bind.execute(
            room_online.update()
            .where(
                sa.and_(
                    room_online.c.property_id == property_id,
                    room_online.c.category_id == category_id,
                )
            )
            .values(room_type_id=room_type_id)
        )

    booking_rows = bind.execute(
        sa.select(bookings.c.id, rooms.c.property_id, rooms.c.category_id)
        .select_from(bookings.join(rooms, bookings.c.room_id == rooms.c.id))
        .where(
            sa.and_(
                bookings.c.requested_room_type_id.is_(None),
                rooms.c.category_id.isnot(None),
            )
        )
    ).fetchall()
    for row in booking_rows:
        room_type_id = room_type_map.get((row.property_id, row.category_id))
        if room_type_id:
            bind.execute(
                bookings.update()
                .where(bookings.c.id == row.id)
                .values(requested_room_type_id=room_type_id)
            )

    mapping_rows = bind.execute(
        sa.select(channel_room_maps.c.id, rooms.c.property_id, rooms.c.category_id)
        .select_from(channel_room_maps.join(rooms, channel_room_maps.c.internal_room_id == rooms.c.id))
        .where(
            sa.and_(
                channel_room_maps.c.internal_room_type_id.is_(None),
                rooms.c.category_id.isnot(None),
            )
        )
    ).fetchall()
    for row in mapping_rows:
        room_type_id = room_type_map.get((row.property_id, row.category_id))
        if room_type_id:
            bind.execute(
                channel_room_maps.update()
                .where(channel_room_maps.c.id == row.id)
                .values(internal_room_type_id=room_type_id)
            )


def upgrade():
    op.create_table(
        'room_types',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('property_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('max_guests', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('max_adults', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('max_children', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_infants', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('property_id', 'name', name='uq_room_types_property_name'),
    )
    op.create_index(op.f('ix_room_types_property_id'), 'room_types', ['property_id'], unique=False)

    with op.batch_alter_table('rooms', schema=None) as batch_op:
        batch_op.add_column(sa.Column('room_type_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_rooms_room_type_id'), ['room_type_id'], unique=False)
        batch_op.create_foreign_key('fk_rooms_room_type_id', 'room_types', ['room_type_id'], ['id'])

    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('requested_room_type_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_bookings_requested_room_type_id'), ['requested_room_type_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_bookings_requested_room_type_id',
            'room_types',
            ['requested_room_type_id'],
            ['id'],
        )

    with op.batch_alter_table('rate_plans', schema=None) as batch_op:
        batch_op.add_column(sa.Column('room_type_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_rate_plans_room_type_id'), ['room_type_id'], unique=False)
        batch_op.create_foreign_key('fk_rate_plans_room_type_id', 'room_types', ['room_type_id'], ['id'])
        batch_op.alter_column('category_id', existing_type=sa.Integer(), nullable=True)

    with op.batch_alter_table('room_online', schema=None) as batch_op:
        batch_op.add_column(sa.Column('room_type_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_room_online_room_type_id'), ['room_type_id'], unique=False)
        batch_op.create_foreign_key('fk_room_online_room_type_id', 'room_types', ['room_type_id'], ['id'])
        batch_op.alter_column('category_id', existing_type=sa.Integer(), nullable=True)

    with op.batch_alter_table('channel_room_maps', schema=None) as batch_op:
        batch_op.add_column(sa.Column('internal_room_type_id', sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_channel_room_maps_internal_room_type_id'),
            ['internal_room_type_id'],
            unique=False,
        )
        batch_op.create_foreign_key(
            'fk_channel_room_maps_internal_room_type_id',
            'room_types',
            ['internal_room_type_id'],
            ['id'],
        )

    _backfill_room_types()


def downgrade():
    with op.batch_alter_table('channel_room_maps', schema=None) as batch_op:
        batch_op.drop_constraint('fk_channel_room_maps_internal_room_type_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_channel_room_maps_internal_room_type_id'))
        batch_op.drop_column('internal_room_type_id')

    with op.batch_alter_table('room_online', schema=None) as batch_op:
        batch_op.alter_column('category_id', existing_type=sa.Integer(), nullable=False)
        batch_op.drop_constraint('fk_room_online_room_type_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_room_online_room_type_id'))
        batch_op.drop_column('room_type_id')

    with op.batch_alter_table('rate_plans', schema=None) as batch_op:
        batch_op.alter_column('category_id', existing_type=sa.Integer(), nullable=False)
        batch_op.drop_constraint('fk_rate_plans_room_type_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_rate_plans_room_type_id'))
        batch_op.drop_column('room_type_id')

    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.drop_constraint('fk_bookings_requested_room_type_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_bookings_requested_room_type_id'))
        batch_op.drop_column('requested_room_type_id')

    with op.batch_alter_table('rooms', schema=None) as batch_op:
        batch_op.drop_constraint('fk_rooms_room_type_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_rooms_room_type_id'))
        batch_op.drop_column('room_type_id')

    op.drop_index(op.f('ix_room_types_property_id'), table_name='room_types')
    op.drop_table('room_types')
