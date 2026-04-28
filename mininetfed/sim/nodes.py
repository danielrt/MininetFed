import shlex
from pathlib import Path
import os
import pty
import select
import json
from subprocess import check_output

import docker
from docker.errors import ImageNotFound

from mininet.node import Node, Host
from mininet.log import info, error, warn, debug

from mininetfed.sim.term import makeTerm
from mininetfed.sim.util.docker_utils import docker_image_exists, build_fed_broker_docker_image, \
    build_fed_node_docker_image, MININETFED_IMAGE_INSTALL_LOCATION

DOCKER_NODE_FOLDER = "/flw"

class Docker(Host):
    """Node that represents a docker container.
    This part is inspired by:
    http://techandtrains.com/2014/08/21/docker-container-as-mininet-host/
    We use the docker-py client library to control docker.
    """

    def __init__(self, name, dimage=None, dcmd=None, did=None, **kwargs):
        """
        Creates a Docker container as Mininet host.

        Resource limitations based on CFS scheduler:
        * cpu.cfs_quota_us: the total available run-time within a period (in microseconds)
        * cpu.cfs_period_us: the length of a period (in microseconds)
        (https://www.kernel.org/doc/Documentation/scheduler/sched-bwc.txt)

        Default Docker resource limitations:
        * cpu_shares: Relative amount of max. avail CPU for container
            (not a hard limit, e.g. if only one container is busy and the rest idle)
            e.g. usage: d1=4 d2=6 <=> 40% 60% CPU
        * cpuset_cpus: Bind containers to CPU 0 = cpu_1 ... n-1 = cpu_n (string: '0,2')
        * mem_limit: Memory limit (format: <number>[<unit>], where unit = b, k, m or g)
        * memswap_limit: Total limit = memory + swap

        All resource limits can be updated at runtime! Use:
        * updateCpuLimits(...)
        * updateMemoryLimits(...)
        """
        self.dimage = dimage
        self.dnameprefix = "mn"
        self.dcmd = dcmd if dcmd is not None else "/bin/bash"
        self.dc = None  # pointer to the dict containing 'Id' and 'Warnings' keys of the container
        self.dcinfo = None
        self.func = []
        self.did = did  # Id of running container
        #  let's store our resource limits to have them available through the
        #  Mininet API later on
        defaults = { 'cpu_quota': -1,
                     'cpu_period': None,
                     'cpu_shares': None,
                     'cpuset_cpus': None,
                     'mem_limit': None,
                     'memswap_limit': None,
                     'environment': {},
                     'volumes': [],  # use ["/home/user1/:/mnt/vol2:rw"]
                     'tmpfs': [],  # use ["/home/vol1/:size=3G,uid=1000"]
                     'network_mode': None,
                     'privileged': False,
                     'publish_all_ports': True,
                     'port_bindings': {},
                     'ports': [],
                     'dns': [],
                     'user': "0:0",
                     'ipc_mode': None,
                     'devices': [],
                     'cap_add': ['net_admin'],  # we need this to allow mininet network setup
                     #'storage_opt': None,
                     'sysctls': {}
                     }
        defaults.update( kwargs )

        if 'net_admin' not in defaults['cap_add']:
            defaults['cap_add'] += ['net_admin']  # adding net_admin if it's cleared out to allow mininet network setup

        # keep resource in a dict for easy update during container lifetime
        self.resources = dict(
            cpu_quota=defaults['cpu_quota'],
            cpu_period=defaults['cpu_period'],
            cpu_shares=defaults['cpu_shares'],
            cpuset_cpus=defaults['cpuset_cpus'],
            mem_limit=defaults['mem_limit'],
            memswap_limit=defaults['memswap_limit']
        )

        self.volumes = defaults['volumes']
        self.tmpfs = defaults['tmpfs']
        self.environment = {} if defaults['environment'] is None else defaults['environment']
        # setting PS1 at "docker run" may break the python docker api (update_container hangs...)
        # self.environment.update({"PS1": chr(127)})  # CLI support
        self.network_mode = defaults['network_mode']
        self.privileged = defaults['privileged']
        self.publish_all_ports = defaults['publish_all_ports']
        self.port_bindings = defaults['port_bindings']
        self.dns = defaults['dns']
        self.user = defaults['user']
        self.ipc_mode = defaults['ipc_mode']
        self.devices = defaults['devices']
        self.cap_add = defaults['cap_add']
        self.sysctls = defaults['sysctls']
        #self.storage_opt = defaults['storage_opt']

        # setup docker client
        # self.dcli = docker.APIClient(base_url='unix://var/run/docker.sock')
        self.dcli = docker.from_env().api

        # pull image if it does not exist
        if self.dimage:
            self._check_image_exists(dimage, True)

        # for DEBUG
        debug("Created docker container object %s\n" % name)
        debug("image: %s\n" % str(self.dimage))
        debug("dcmd: %s\n" % str(self.dcmd))
        #info("%s: kwargs %s\n" % (name, str(kwargs)))

        # creats host config for container
        # see: https://docker-py.readthedocs.org/en/latest/hostconfig/
        hc = self.dcli.create_host_config(
            network_mode=self.network_mode,
            privileged=self.privileged,
            binds=self.volumes,
            tmpfs=self.tmpfs,
            publish_all_ports=self.publish_all_ports,
            port_bindings=self.port_bindings,
            mem_limit=self.resources.get('mem_limit'),
            cpuset_cpus=self.resources.get('cpuset_cpus'),
            dns=self.dns,
            ipc_mode=self.ipc_mode,  # string
            devices=self.devices,  # see docker-py docu
            cap_add=self.cap_add,  # see docker-py docu
            sysctls=self.sysctls,  # see docker-py docu
            #storage_opt=self.storage_opt
        )

        if kwargs.get("rm", False):
            container_list = self.dcli.containers(all=True)
            for container in container_list:
                for container_name in container.get("Names", []):
                    if "%s.%s" % (self.dnameprefix, name) in container_name:
                        self.dcli.remove_container(container="%s.%s" % (self.dnameprefix, name), force=True)
                        break

        if self.did:
            self.dc = {'Id': '{}'.format(self.did), 'Warnings': []}
            self.existing_container = 1
        else:
            # create new docker container
            self.dc = self.dcli.create_container(
                name="%s.%s" % (self.dnameprefix, name),
                image=self.dimage,
                command=self.dcmd,
                entrypoint=list(),  # overwrite (will be executed manually at the end)
                stdin_open=True,  # keep container open
                tty=True,  # allocate pseudo tty
                environment=self.environment,
                #network_disabled=True,  # docker stats breaks if we disable the default network
                host_config=hc,
                user=self.user,
                ports=defaults['ports'],
                labels=['com.containernet'],
                volumes=[self._get_volume_mount_name(v) for v in self.volumes if self._get_volume_mount_name(v) is not None],
                hostname=name
            )

        # start the container
        self.dcli.start(self.dc)
        debug("Docker container %s started\n" % name)

        # fetch information about new container
        self.dcinfo = self.dcli.inspect_container(self.dc)
        self.did = self.dcinfo.get("Id")

        # call original Node.__init__
        Node.__init__(self, name, **kwargs)

        # let's initially set our resource limits
        self.update_resources(**self.resources)

    def start(self):
        # Containernet ignores the CMD field of the Dockerfile.
        # Lets try to load it here and manually execute it once the
        # container is started and configured by Containernet:
        cmd_field = self.get_cmd_field(self.dimage)
        entryp_field = self.get_entrypoint_field(self.dimage)
        if entryp_field is not None:
            if cmd_field is None:
                cmd_field = list()
            # clean up cmd_field
            try:
                cmd_field.remove(u'/bin/sh')
                cmd_field.remove(u'-c')
            except ValueError:
                pass
            # we just add the entryp. commands to the beginning:
            cmd_field = entryp_field + cmd_field
        if cmd_field is not None:
            cmd_field.append("> /dev/pts/0 2>&1")  # make output available to docker logs
            cmd_field.append("&")  # put to background (works, but not nice)
            #info("{}: running CMD: {}\n".format(self.name, cmd_field))
            self.cmd(" ".join(cmd_field))

    def get_cmd_field(self, imagename):
        """
        Try to find the original CMD command of the Dockerfile
        by inspecting the Docker image.
        Returns list from CMD field if it is different from
        a single /bin/bash command which Containernet executes
        anyhow.
        """
        try:
            imgd = self.dcli.inspect_image(imagename)
            cmd = imgd.get("Config", {}).get("Cmd")
            assert isinstance(cmd, list)
            # filter the default case: a single "/bin/bash"
            if "/bin/bash" in cmd and len(cmd) == 1:
                return None
            return cmd
        except BaseException as ex:
            error("Error during image inspection of {}:{}"
                  .format(imagename, ex))
        return None

    def get_entrypoint_field(self, imagename):
        """
        Try to find the original ENTRYPOINT command of the Dockerfile
        by inspecting the Docker image.
        Returns list or None.
        """
        try:
            imgd = self.dcli.inspect_image(imagename)
            ep = imgd.get("Config", {}).get("Entrypoint")
            if isinstance(ep, list) and len(ep) < 1:
                return None
            return ep
        except BaseException as ex:
            error("Error during image inspection of {}:{}"
                  .format(imagename, ex))
        return None

    # Command support via shell process in namespace
    def startShell( self, *args, **kwargs ):
        "Start a shell process for running commands"
        if self.shell:
            error( "%s: shell is already running\n" % self.name )
            return
        # mnexec: (c)lose descriptors, (d)etach from tty,
        # (p)rint pid, and run in (n)amespace
        # opts = '-cd' if mnopts is None else mnopts
        # if self.inNamespace:
        #     opts += 'n'
        # bash -i: force interactive
        # -s: pass $* to shell, and make process easy to find in ps
        # prompt is set to sentinel chr( 127 )
        if hasattr(self, 'existing_container'):
            cmd = ['docker', 'exec', '-it', '%s' % self.did, 'env', 'PS1=' + chr(127),
                   'bash', '--norc', '-is', 'mininet:' + self.name]
        else:
            cmd = ['docker', 'exec', '-it', '%s.%s' % (self.dnameprefix, self.name), 'env', 'PS1=' + chr(127),
                   'bash', '--norc', '-is', 'mininet:' + self.name]
        # Spawn a shell subprocess in a pseudo-tty, to disable buffering
        # in the subprocess and insulate it from signals (e.g. SIGINT)
        # received by the parent
        self.master, self.slave = pty.openpty()
        self.shell = self._popen( cmd, stdin=self.slave, stdout=self.slave, stderr=self.slave,
                                  close_fds=False )
        self.stdin = os.fdopen( self.master, 'r' )
        self.stdout = self.stdin
        self.pid = self._get_pid()
        self.pollOut = select.poll()
        self.pollOut.register( self.stdout )
        # Maintain mapping between file descriptors and nodes
        # This is useful for monitoring multiple nodes
        # using select.poll()
        self.outToNode[ self.stdout.fileno() ] = self
        self.inToNode[ self.stdin.fileno() ] = self
        self.execed = False
        self.lastCmd = None
        self.lastPid = None
        self.readbuf = ''
        # Wait for prompt
        while True:
            data = self.read( 1024 )
            if data[ -1 ] == chr( 127 ):
                break
            self.pollOut.poll()
        self.waiting = False
        # +m: disable job control notification
        self.cmd( 'unset HISTFILE; stty -echo; set +m' )

    def _get_volume_mount_name(self, volume_str):
        """ Helper to extract mount names from volume specification strings """
        parts = volume_str.split(":")
        if len(parts) < 3:
            return None
        return parts[1]

    def terminate( self ):
        """ Stop docker container """
        if not self._is_container_running():
            return
        try:
            if not hasattr(self, 'existing_container'):
                self.dcli.remove_container(self.dc, force=True, v=True)
        except docker.errors.APIError:
            warn("Warning: API error during container removal.\n")

        self.cleanup()

    def sendCmd( self, *args, **kwargs ):
        """Send a command, followed by a command to echo a sentinel,
           and return without waiting for the command to complete."""
        self._check_shell()
        if not self.shell:
            return
        Host.sendCmd( self, *args, **kwargs )

    def popen( self, *args, **kwargs ):
        """Return a Popen() object in node's namespace
           args: Popen() args, single list, or string
           kwargs: Popen() keyword args"""
        if not self._is_container_running():
            error( "ERROR: Can't connect to Container \'%s\'' for docker host \'%s\'!\n" % (self.did, self.name) )
            return
        mncmd = ["docker", "exec", "-t", "%s.%s" % (self.dnameprefix, self.name)]
        return Node.popen( self, *args, mncmd=mncmd, **kwargs )

    def cmd(self, *args, **kwargs ):
        """Send a command, wait for output, and return it.
           cmd: string"""
        verbose = kwargs.get( 'verbose', False )
        log = info if verbose else debug
        log( '*** %s : %s\n' % ( self.name, args ) )
        self.sendCmd( *args, **kwargs )
        return self.waitOutput( verbose )

    def _get_pid(self):
        state = self.dcinfo.get("State", None)
        if state:
            return state.get("Pid", -1)
        return -1

    def _check_shell(self):
        """Verify if shell is alive and
           try to restart if needed"""
        if self._is_container_running():
            if self.shell:
                self.shell.poll()
                if self.shell.returncode is not None:
                    debug("*** Shell died for docker host \'%s\'!\n" % self.name )
                    self.shell = None
                    debug("*** Restarting Shell of docker host \'%s\'!\n" % self.name )
                    self.startShell()
            else:
                debug("*** Restarting Shell of docker host \'%s\'!\n" % self.name )
                self.startShell()
        else:
            error( "ERROR: Can't connect to Container \'%s\'' for docker host \'%s\'!\n" % (self.did, self.name) )
            if self.shell:
                self.shell = None

    def _is_container_running(self):
        """Verify if container is alive"""
        container_list = self.dcli.containers(filters={"id": self.did, "status": "running"})
        if len(container_list) == 0:
            return False;
        return True

    def _check_image_exists(self, imagename, pullImage=False):
        # split tag from repository if a tag is specified
        if ":" in imagename:
            #If two :, then the first is to specify a port. Otherwise, it must be a tag
            slices = imagename.split(":")
            repo = ":".join(slices[0:-1])
            tag = slices[-1]
        else:
            repo = imagename
            tag = "latest"

        if self._image_exists(repo, tag):
            return True

        # image not found
        if pullImage:
            if self._pull_image(repo, tag):
                info('*** Download of "%s:%s" successful\n' % (repo, tag))
                return True
        # we couldn't find the image
        return False

    def _image_exists(self, repo, tag):
        """
        Checks if the repo:tag image exists locally
        :return: True if the image exists locally. Else false.
        """
        # filter by repository
        images = self.dcli.images(repo)
        imageName = "%s:%s" % (repo, tag)

        for image in images:
            if 'RepoTags' in image:
                if image['RepoTags'] is None:
                    return False
                if imageName in image['RepoTags']:
                    return True
        return False

    def _pull_image(self, repository, tag):
        """
        :return: True if pull was successful. Else false.
        """
        try:
            info('*** Image "%s:%s" not found. Trying to load the image. \n' % (repository, tag))
            info('*** This can take some minutes...\n')

            message = ""
            for line in self.dcli.pull(repository, tag, stream=True):
                # Collect output of the log for enhanced error feedback
                message = message + json.dumps(json.loads(line), indent=4)

        except:
            error('*** error: _pull_image: %s:%s failed.' % (repository, tag)
                  + message)
        if not self._image_exists(repository, tag):
            error('*** error: _pull_image: %s:%s failed.' % (repository, tag)
                  + message)
            return False
        return True

    def update_resources(self, **kwargs):
        """
        Update the container's resources using the docker.update function
        re-using the same parameters:
        Args:
           blkio_weight
           cpu_period, cpu_quota, cpu_shares
           cpuset_cpus
           cpuset_mems
           mem_limit
           mem_reservation
           memswap_limit
           kernel_memory
           restart_policy
        see https://docs.docker.com/engine/reference/commandline/update/
        or API docs: https://docker-py.readthedocs.io/en/stable/api.html#module-docker.api.container
        :return:
        """

        self.resources.update(kwargs)
        # filter out None values to avoid errors
        resources_filtered = {res:self.resources[res] for res in self.resources if self.resources[res] is not None}
        #info("{1}: update resources {0}\n".format(resources_filtered, self.name))
        self.dcli.update_container(self.dc, **resources_filtered)

    def updateCpuLimit(self, cpu_quota=-1, cpu_period=-1, cpu_shares=-1, cores=None):
        """
        Update CPU resource limitations.
        This method allows to update resource limitations at runtime by bypassing the Docker API
        and directly manipulating the cgroup options.
        Args:
            cpu_quota: cfs quota us
            cpu_period: cfs period us
            cpu_shares: cpu shares
            cores: specifies which cores should be accessible for the container e.g. "0-2,16" represents
                Cores 0, 1, 2, and 16
        """
        # see https://www.kernel.org/doc/Documentation/scheduler/sched-bwc.txt

        # also negative values can be set for cpu_quota (uncontrained setting)
        # just check if value is a valid integer
        if isinstance(cpu_quota, int):
            self.resources['cpu_quota'] = self.cgroupSet("cfs_quota_us", cpu_quota)
        if cpu_period >= 0:
            self.resources['cpu_period'] = self.cgroupSet("cfs_period_us", cpu_period)
        if cpu_shares >= 0:
            self.resources['cpu_shares'] = self.cgroupSet("shares", cpu_shares)
        if cores:
            self.dcli.update_container(self.dc, cpuset_cpus=cores)
            # quota, period ad shares can also be set by this line. Usable for future work.

    def updateMemoryLimit(self, mem_limit=-1, memswap_limit=-1):
        """
        Update Memory resource limitations.
        This method allows to update resource limitations at runtime by bypassing the Docker API
        and directly manipulating the cgroup options.

        Args:
            mem_limit: memory limit in bytes
            memswap_limit: swap limit in bytes

        """
        # see https://www.kernel.org/doc/Documentation/scheduler/sched-bwc.txt
        if mem_limit >= 0:
            self.resources['mem_limit'] = self.cgroupSet("limit_in_bytes", mem_limit, resource="memory")
        if memswap_limit >= 0:
            self.resources['memswap_limit'] = self.cgroupSet("memsw.limit_in_bytes", memswap_limit, resource="memory")


    def cgroupSet(self, param, value, resource='cpu'):
        """
        Directly manipulate the resource settings of the Docker container's cgrpup.
        Args:
            param: parameter to set, e.g., cfs_quota_us
            value: value to set
            resource: resource name: cpu

        Returns: value that was set

        """
        cmd = 'cgset -r %s.%s=%s docker/%s' % (
            resource, param, value, self.did)
        debug(cmd + "\n")
        try:
            check_output(cmd, shell=True)
        except:
            error("Problem writing cgroup setting %r\n" % cmd)
            return
        nvalue = int(self.cgroupGet(param, resource))
        if nvalue != value:
            error('*** error: cgroupSet: %s set to %s instead of %s\n'
                  % (param, nvalue, value))
        return nvalue

    def cgroupGet(self, param, resource='cpu'):
        """
        Read cgroup values.
        Args:
            param: parameter to read, e.g., cfs_quota_us
            resource: resource name: cpu / memory

        Returns: value

        """
        cmd = 'cgget -r %s.%s docker/%s' % (
            resource, param, self.did)
        try:
            return int(check_output(cmd, shell=True).split()[-1])
        except:
            error("Problem reading cgroup info: %r\n" % cmd)
            return -1


class DockerFedNode(Docker):
    """Base class for Dockerized MininetFed nodes."""

    def __init__(self, name: str, node_folder: str, dimage: str, **kwargs):
        abs_folder_path = os.path.abspath(node_folder)
        volumes = [f"{abs_folder_path}:{DOCKER_NODE_FOLDER}:rw"]

        if not dimage:
            raise ImageNotFound("No Docker image was provided.")

        if not docker_image_exists(dimage):
            raise ImageNotFound(f"Docker image {dimage} was not found.")

        self.executor_processes = []
        Docker.__init__(self, name=name, dimage=dimage, volumes=volumes, **kwargs)

    @staticmethod
    def _cleanup_host_files(host_folder: Path, wait_for_done: bool = True) -> None:
        """Remove stale execution files from previous runs."""
        files = ["out.txt", "err.txt", "exit_code.txt"]
        if wait_for_done:
            files.append(".done")

        for filename in files:
            (host_folder / filename).unlink(missing_ok=True)

    def _run_executor(
        self,
        *,
        node_label: str,
        script: str,
        node_id: str,
        broker_addr: str,
        node_args: dict | None,
        host_folder: Path,
        show_term: bool = True,
        wait_for_done: bool = True,
    ) -> Path | None:
        """
        Run mininetfed-node-executor either in a GUI terminal or in headless mode.

        Files written inside the mounted folder:
        - out.txt: stdout
        - err.txt: stderr
        - exit_code.txt: process exit code
        - .done: completion marker, only when wait_for_done=True
        """
        self._cleanup_host_files(host_folder, wait_for_done=wait_for_done)

        args_json = shlex.quote(json.dumps(node_args or {}))
        done_file = f"{DOCKER_NODE_FOLDER}/.done"
        out_file = f"{DOCKER_NODE_FOLDER}/out.txt"
        err_file = f"{DOCKER_NODE_FOLDER}/err.txt"
        exit_code_file = f"{DOCKER_NODE_FOLDER}/exit_code.txt"

        executor_cmd = (
            f"mininetfed-node-executor "
            f"--file {shlex.quote(script)} "
            f"--node_id {shlex.quote(node_id)} "
            f"--broker_addr {shlex.quote(broker_addr)} "
            f"--node_folder {DOCKER_NODE_FOLDER} "
            f"--node_args-json {args_json}"
        )

        done_cmd = f"echo DONE > {shlex.quote(done_file)}" if wait_for_done else ":"

        if show_term:
            # Keep stdout/stderr visible in the GUI terminal and also persist them to files.
            # Requires bash, which is already used through bash -lc.
            inner_cmd = (
                "umask 000; "
                f"rm -f {out_file} {err_file} {exit_code_file} {done_file}; "
                f"PYTHONUNBUFFERED=1 {executor_cmd} "
                f"2> >(tee -a {err_file} >&2) | tee -a {out_file}; "
                "exit_code=${PIPESTATUS[0]}; "
                f"echo $exit_code > {exit_code_file}; "
                f"{done_cmd}; "
                "exec bash"
            )
            cmd = f"bash -lc {shlex.quote(inner_cmd)}"
            print(f"[{node_label}] Opening GUI terminal with: {cmd}")
            processes = makeTerm(self, cmd=cmd) or []
        else:
            # Headless execution: no xterm/gnome-terminal. Output is stored in files.
            inner_cmd = (
                "umask 000; "
                f"rm -f {out_file} {err_file} {exit_code_file} {done_file}; "
                f"PYTHONUNBUFFERED=1 {executor_cmd} > {out_file} 2> {err_file}; "
                "exit_code=$?; "
                f"echo $exit_code > {exit_code_file}; "
                f"{done_cmd}"
            )
            cmd = f"bash -lc {shlex.quote(inner_cmd)}"
            print(f"[{node_label}] Running headless with: {cmd}")
            proc = self.popen(cmd, shell=True)
            processes = [proc] if proc is not None else []

        self.executor_processes.extend(processes)
        return host_folder / ".done" if wait_for_done else None

    def run(self, broker_addr: str, show_term: bool = True) -> Path | None:
        raise NotImplementedError


class FedClientNode(DockerFedNode):
    """Node that represents a Dockerized MininetFed client."""

    def __init__(
        self,
        name: str,
        script: str,
        client_folder: str,
        dimage: str | None = None,
        client_args: dict | None = None,
        **kwargs,
    ):
        self.client_id = name
        self.client_folder = Path(client_folder).resolve()

        if script and len(script):
            self.script = f"{DOCKER_NODE_FOLDER}/{script}"
        else:
            raise FileNotFoundError(f"No execution script was provided for client {self.client_id}")

        self.client_args = client_args or {}

        super().__init__(
            name=name,
            node_folder=str(self.client_folder),
            dimage=dimage,
            **kwargs,
        )
        self.cmd("ifconfig eth0 down")

    def run(self, broker_addr: str, show_term: bool = True) -> Path | None:
        self.cmd(f"route add default gw {broker_addr}")
        return self._run_executor(
            node_label="FedClientNode",
            script=self.script,
            node_id=self.client_id,
            broker_addr=broker_addr,
            node_args=self.client_args,
            host_folder=self.client_folder,
            show_term=show_term,
            wait_for_done=True,
        )


class FedServerNode(DockerFedNode):
    """Node that represents a Dockerized MininetFed server."""

    def __init__(
        self,
        name: str,
        script: str | None = None,
        server_folder: str | None = None,
        dimage: str | None = None,
        server_args: dict | None = None,
        **kwargs,
    ):
        self.server_id = name

        if script and len(script):
            self.script = f"{DOCKER_NODE_FOLDER}/{script}"
        else:
            self.script = f"{MININETFED_IMAGE_INSTALL_LOCATION}/core/nodes/default_fed_server.py"

        self.server_folder = Path(server_folder).resolve() if server_folder else (Path.cwd() / "server_output").resolve()
        self.server_folder.mkdir(parents=True, exist_ok=True)

        self.server_args = server_args or {}

        server_docker_image = dimage or build_fed_node_docker_image("server")["tag"]

        super().__init__(
            name=name,
            node_folder=str(self.server_folder),
            dimage=server_docker_image,
            **kwargs,
        )
        self.cmd("ifconfig eth0 down")

    def run(self, broker_addr: str, show_term: bool = True) -> Path | None:
        self.cmd(f"route add default gw {broker_addr}")
        return self._run_executor(
            node_label="FedServerNode",
            script=self.script,
            node_id=self.server_id,
            broker_addr=broker_addr,
            node_args=self.server_args,
            host_folder=self.server_folder,
            show_term=show_term,
            wait_for_done=True,
        )


class FedBrokerNode(DockerFedNode):
    """Node that represents a Dockerized MininetFed broker."""

    def __init__(
        self,
        name: str,
        broker_folder: str | None = None,
        dimage: str | None = None,
        broker_args: dict | None = None,
        **kwargs,
    ):
        self.broker_id = name
        self.script = f"{MININETFED_IMAGE_INSTALL_LOCATION}/core/nodes/default_fed_broker.py"
        self.broker_folder = Path(broker_folder).resolve() if broker_folder else (Path.cwd() / "broker_output").resolve()
        self.broker_folder.mkdir(parents=True, exist_ok=True)
        self.broker_args = broker_args or {}

        broker_docker_image = dimage or build_fed_broker_docker_image()["tag"]

        super().__init__(
            name=name,
            node_folder=str(self.broker_folder),
            dimage=broker_docker_image,
            **kwargs,
        )
        self.cmd("iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE")

    def run(self, broker_addr: str = "", show_term: bool = True) -> Path | None:
        broker_addr = self.IP(intf=f"{self.broker_id}-eth0")
        return self._run_executor(
            node_label="FedBrokerNode",
            script=self.script,
            node_id=self.broker_id,
            broker_addr=broker_addr,
            node_args=self.broker_args,
            host_folder=self.broker_folder,
            show_term=show_term,
            wait_for_done=False,
        )