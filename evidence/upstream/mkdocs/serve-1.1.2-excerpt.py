# Exact relevant excerpt from mkdocs/commands/serve.py at tag 1.1.2.
def _livereload(host, port, config, builder, site_dir):
    from livereload import Server
    import livereload.handlers

    class LiveReloadServer(Server):
        pass

    server = LiveReloadServer()
    server.watch(config['docs_dir'], builder)
    server.watch(config['config_file_path'], builder)
    for d in config['theme'].dirs:
        server.watch(d, builder)
    server = config['plugins'].run_event('serve', server, config=config, builder=builder)
    server.serve(root=site_dir, host=host, port=port, restart_delay=0)
