import os

from streamseeker.api.core.logger import Logger
logger = Logger().setup(__name__)

# read_check = os.access('requirements.txt', os.R_OK)
# write_check = os.access('requirements.txt', os.W_OK)

# if read_check and write_check:
#     logger.debug("Read and write access granted")
# else:
#     logger.error("Read and write access denied")
#     exit(1)

class OutputHandler:
    def __init__(self, file_path):
        self.file_path = file_path
        self._create_file_if_not_exists(file_path)

    def write_line(self, data):
        with open(self.file_path, 'a') as f:
            f.write(f"{data}\n")
            f.close()
    
    def write_lines(self, data: list[str], mode='w'):
        with open(self.file_path, mode) as f:
            for line in data:
                line = line.strip('\n')
                f.write(f"{line}\n")
            f.close()
    
    def write_bytes(self, data):
        with open(self.file_path, 'ab') as f:
            f.write(data)
            f.close()

    def read_lines(self) -> list[str]:
        with open(self.file_path, 'r') as f:
            data = f.readlines()
            f.close()
            return data
    
    def _create_file_if_not_exists(self, file_path):
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        if not os.path.isfile(file_path):
            logger.info(f"Creating file: {file_path}")
            with open(file_path, 'w') as f:
                f.close()

    def _delete_file_if_exists(self, file_path):
        if os.path.isfile(file_path):
            os.remove(file_path)
            logger.info(f"Deleted file: {file_path}")
        else:
            logger.info(f"File does not exist: {file_path}")