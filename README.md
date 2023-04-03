# Charmed NFS Client Operator

> Warning: This charm is currently under heavy feature development and 
> is subject to breaking changes. It should not be used for production-level
> deployments until a stable version of this charm is released.

## Description

This subordinate charmed operator manages instantiation and 
operations specific to client environments that mount exported NFS shares.

Network File System (NFS) is a distributed file system protocol for
sharing files between heterogeneous environments over a network. This
charm embeds the `nfs-common` package that contains several NFS support
files common to both NFS clients and serves. This charmed operator uses
these support files to mount exported NFS shares.

This charm operator is also a subordinate charm, so it must be integrated with
a principle charm to be fully deployed. Also, this charm should not be deployed 
on top of LXD container-based substrates as LXD containers need to be 
super-privileged and have several AppArmor profile modifications to successfully 
mount NFS shares.

## Usage

_Work-in-progress..._

## Integrations

### _`nfs-share`_

Integrate an NFS server and client over the `nfs_share` interface. This integration
is used to request NFS shares and inform the client when to mount or unmount an
exported NFS share.

### _`juju-info`_

Integrate Charmed NFS Client Operator with a principle charm.

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on 
enhancements to this charm following best practice guidelines, and 
CONTRIBUTING.md for developer guidance.

## License

The Charmed NFS Client Operator is free software, distributed under the Apache
Software License, version 2.0. See LICENSE for more information. It embeds
the `nfs-common` package, which contains files [licensed](http://git.linux-nfs.org/?p=steved/nfs-utils.git;a=blob;f=COPYING;h=941c87de278af88468e104290d62809713ee9ab3;hb=HEAD) 
under the GNU GPLv2 license.
