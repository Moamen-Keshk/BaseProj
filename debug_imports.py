import traceback
import os
from flask import Blueprint, Flask

# 1. Intercept Route Registration
original_route = Blueprint.route
def debug_route(self, *args, **kwargs):
    if self.name == 'channel_manager':
        print(f"\n--- [DEBUG] Route being added to 'channel_manager': {args[0]} ---")
        # Print the last 10 calls to see who imported this
        traceback.print_stack(limit=10)
    return original_route(self, *args, **kwargs)

Blueprint.route = debug_route

# 2. Intercept Blueprint Registration
original_register = Flask.register_blueprint
def debug_register(self, blueprint, **options):
    if blueprint.name == 'channel_manager':
        print(f"\n--- [DEBUG] Flask is registering blueprint: {blueprint.name} ---")
        traceback.print_stack(limit=10)
    return original_register(self, blueprint, **options)

Flask.register_blueprint = debug_register

# 3. Attempt to load the app
try:
    print("Attempting to initialize the app factory...")
    # Set your env var if necessary
    os.environ['FLASK_CONFIG'] = 'default'
    from app import create_app
    app = create_app('default')
    print("\n✅ App created successfully without errors!")
except Exception as e:
    print("\n❌ CRASH DETECTED")
    traceback.print_exc()