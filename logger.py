import click


class Logger:
    def __init__(self, is_quiet, output_file):
        self._is_quiet = is_quiet
        self._output_file = output_file

        self._clear_output_file()


    def log(self, message):
        if not self._is_quiet:
            click.echo(message)
        if self._output_file:
            with open(self._output_file, 'a') as out:
                out.write(message)


    def _clear_output_file(self):
        if self._output_file:
            open(self._output_file, 'w').close()
