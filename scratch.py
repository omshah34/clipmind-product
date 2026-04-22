import asyncio
from api.main import app

for route in app.routes:
    if hasattr(route, 'path') and 'preview' in route.path:
        print(f"Route: {route.path}")
        if hasattr(route, 'dependant'):
            for p in route.dependant.path_params:
                print(f"Path param: {p.name}, type: {p.field_info.annotation}")
        break
