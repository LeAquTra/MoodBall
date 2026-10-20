from django.urls import path

from . import views

app_name = "mcp"

urlpatterns = [
    path("mcp/servers/", views.mcp_servers, name="servers"),
    path("mcp/servers/<uuid:server_id>/", views.mcp_server_detail, name="server-detail"),
    path("mcp/servers/<uuid:server_id>/test/", views.mcp_server_test, name="server-test"),
    path("mcp/servers/<uuid:server_id>/refresh/", views.mcp_server_refresh, name="server-refresh"),
    path("mcp/import/", views.mcp_import, name="import"),
    path("mcp/export/", views.mcp_export, name="export"),
    path("tools/", views.tools_view, name="tools"),
    path("tools/refresh/", views.tools_refresh, name="tools-refresh"),
    path("tools/<str:name>/toggle/", views.tool_toggle, name="tool-toggle"),
    path("tools/<str:name>/invoke/", views.tool_invoke, name="tool-invoke"),
]
