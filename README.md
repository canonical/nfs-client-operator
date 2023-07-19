<div align="center">

# NFS client operator

A subordinate [Juju](https://juju.is) operator for requesting and mounting exported NFS shares on virtual machines. 

[![Charmhub Badge](https://charmhub.io/nfs-client/badge.svg)](https://charmhub.io/nfs-client)
[![CI](https://github.com/canonical/nfs-client-operator/actions/workflows/ci.yaml/badge.svg)](https://github.com/canonical/nfs-client-operator/actions/workflows/ci.yaml/badge.svg)
[![Release](https://github.com/canonical/nfs-client-operator/actions/workflows/release.yaml/badge.svg)](https://github.com/canonical/nfs-client-operator/actions/workflows/release.yaml/badge.svg)
[![Matrix](https://img.shields.io/matrix/ubuntu-hpc%3Amatrix.org?logo=matrix&label=ubuntu-hpc)](https://matrix.to/#/#ubuntu-hpc:matrix.org)

</div>

## Features

The NFS client operator requests and mounts exported NFS shares on virtual machines. This operator embeds the `nfs-common` 
package which contains several support files common to both NFS clients and servers. Network File System (NFS) itself is a 
distributed file system protocol for sharing files between heterogeneous environments over a network.

## Usage

NFS client operator is a subordinate operator; it must be integrated with a principle operator for 
it to deploy successfully. For more information on how Juju operators work and how manage them, please refer to 
the [Juju documentation](https://juju.is/docs/juju/manage-applications). This operator should be used with 
Juju 3.x or greater.

#### With NFS server proxy operator

```shell
$ juju deploy nfs-server-proxy --config endpoint=nfs://12.34.56.78/data
$ juju deploy nfs-client data --config mountpoint=/data
$ juju deploy ubuntu base --base ubuntu@22.04
$ juju integrate data:juju-info base:juju-info
$ juju integrate data:nfs-share nfs-server-proxy:nfs-server-proxy
```

#### With LXD containers

If you are deploying Juju operators to an LXD container-based cloud substrate, you must modify the default LXD profile. 
The LXD containers must be super-privileged and have their AppArmor profile modified to allow `nfs` and `rpc_pipefs` mounts 
to successfully mount NFS shares. You can use the following commands to modify the default LXD profile to allow NFS mounts:

```shell
$ lxc profile set default security.privileged true
$ lxc profile set default raw.apparmor 'mount fstype=nfs*, mount fstype=rpc_pipefs'
```

## Project & Community

The NFS client operator is a project of the [Ubuntu HPC](https://discourse.ubuntu.com/t/high-performance-computing-team/35988) 
community. It is an open source project that is welcome to community involvement, contributions, suggestions, fixes, and 
constructive feedback. Interested in being involved with the development of the NFS client operator? Check out these links below:

* [Join our online chat](https://matrix.to/#/#ubuntu-hpc:matrix.org)
* [Contributing guidelines](./CONTRIBUTING.md)
* [Code of conduct](https://ubuntu.com/community/ethos/code-of-conduct)
* [File a bug report](https://github.com/canonical/nfs-client-operator/issues)
* [Juju SDK docs](https://juju.is/docs/sdk)

## License

The NFS client operator is free software, distributed under the Apache Software License, version 2.0. See the [LICENSE](./LICENSE) file for more information.
