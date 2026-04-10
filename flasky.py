import os
import sys
import click
from dotenv import load_dotenv

# 1. Load environment variables ONCE, before anything else
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    load_dotenv()

from flask_migrate import Migrate, upgrade
from app import create_app, db, socketio

COV = None
if os.environ.get('FLASK_COVERAGE'):
    import coverage
    COV = coverage.Coverage(branch=True, include=['app/*'])
    COV.start()

app = create_app(os.getenv('FLASK_CONFIG') or 'default')
migrate = Migrate(app, db)

from app.api.models import (
    User,
    Role,
    PMSPermission,
    UserPropertyAccess,
    Notification,
    OrderStatus,
    PropertyStatus,
    RoomStatus,
    PaymentStatus,
    Category,
    BookingStatus,
    Amenity,
    RoomCleaningStatus
)

from app.api.channel_manager.models import SupportedChannel


@app.shell_context_processor
def make_shell_context():
    return dict(
        db=db,
        User=User,
        Role=Role,
        PMSPermission=PMSPermission,
        UserPropertyAccess=UserPropertyAccess,
        Notification=Notification,
        OrderStatus=OrderStatus,
        PropertyStatus=PropertyStatus,
        RoomStatus=RoomStatus,
        PaymentStatus=PaymentStatus,
        BookingStatus=BookingStatus,
        Category=Category,
        SupportedChannel=SupportedChannel,
        RoomCleaningStatus=RoomCleaningStatus,
        Amenity=Amenity
    )


@app.cli.command()
@click.option('--coverage/--no-coverage', default=False, help='Run tests under code coverage.')
@click.argument('test_names', nargs=-1)
def test(coverage, test_names):
    """Run the unit tests."""
    if coverage and not os.environ.get('FLASK_COVERAGE'):
        import subprocess
        os.environ['FLASK_COVERAGE'] = '1'
        sys.exit(subprocess.call(sys.argv))

    import unittest

    if test_names:
        tests = unittest.TestLoader().loadTestsFromNames(test_names)
    else:
        tests = unittest.TestLoader().discover('app/tests')

    result = unittest.TextTestRunner(verbosity=2).run(tests)

    if COV:
        COV.stop()
        COV.save()
        print('Coverage Summary:')
        COV.report()
        basedir = os.path.abspath(os.path.dirname(__file__))
        covdir = os.path.join(basedir, 'tmp', 'coverage')
        os.makedirs(covdir, exist_ok=True)
        COV.html_report(directory=covdir)
        print(f'HTML version: file://{os.path.join(covdir, "index.html")}')
        COV.erase()

    if not result.wasSuccessful():
        sys.exit(1)


@app.cli.command()
@click.option('--length', default=25, help='Number of functions to include in the profiler report.')
@click.option('--profile-dir', default=None, help='Directory where profiler data files are saved.')
def profile(length, profile_dir):
    """Start the application under the code profiler."""
    from werkzeug.middleware.profiler import ProfilerMiddleware

    app.wsgi_app = ProfilerMiddleware(
        app.wsgi_app,
        restrictions=[length],
        profile_dir=profile_dir,
    )
    # Notice we removed the app.run() from inside this function!


@app.cli.command()
def deploy():
    """Run deployment tasks."""
    upgrade()

    Role.insert_roles()
    OrderStatus.insert_status()
    PropertyStatus.insert_status()
    RoomStatus.insert_status()
    PaymentStatus.insert_status()
    BookingStatus.insert_status()
    Category.insert_categories()
    SupportedChannel.insert_channels()
    Amenity.insert_default_amenities()
    RoomCleaningStatus.insert_status()

    print('Deployment tasks completed successfully.')


# ✅ CORRECT: Placed at the very end of the file, at the root indentation level.
if __name__ == '__main__':
    print("🚀 Booting up the Lotel PMS Real-Time Server...")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)