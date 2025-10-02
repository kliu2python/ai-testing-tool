import os

import common.env as env


class Commands:
    def __init__(self, device_type, version):
        self.commands = []
        cmd_file_path = env.get_cmds_file_path(device_type, version)
        if os.path.exists(cmd_file_path):
            self.cmd_config = env.load_config(cmd_file_path)

            for name in self.cmd_config.keys():
                self.__setattr__(
                    f"{name}_cmd", self.__generate_cmd_func(name)
                )
        else:
            raise FileNotFoundError(
                f"Failed to find config file {cmd_file_path}"
            )

    def __generate_cmd_func(self, name):
        def cmd_func(append_ahead=False, **kwargs):
            cmd_name = self.cmd_config.get(name)
            commands = list(map(lambda x: x.format(**kwargs), cmd_name))
            if append_ahead:
                commands.extend(self.commands)
                self.commands = commands
            else:
                self.commands.extend(commands)
        return cmd_func

    def reset_commands(self):
        self.commands = []
