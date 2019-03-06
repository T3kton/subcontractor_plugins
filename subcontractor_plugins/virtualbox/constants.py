class DeviceType:
  Null = 'Null'  # 0
  Floppy = 'Floppy'  # 1
  DVD = 'DVD'  # 2
  HardDisk = 'HardDisk'  # 3
  Network = 'Network'  # 4
  USB = 'USB'  # 5
  SharedFolder = 'SharedFolder'  # 6
  Graphics3D = 'Graphics3D'  # 7


class MachineState:
  Null = 'Null'  # 0
  PoweredOff = 'PoweredOff'  # 1
  Saved = 'Saved'  # 2
  Teleported = 'Teleported'  # 3
  Aborted = 'Aborted'  # 4
  Running = 'Running'  # 5
  FirstOnline = 'FirstOnline'  # 5
  Paused = 'Paused'  # 6
  Stuck = 'Stuck'  # 7
  Teleporting = 'Teleporting'  # 8
  FirstTransient = 'FirstTransient'  # 8
  LiveSnapshotting = 'LiveSnapshotting'  # 9
  Starting = 'Starting'  # 10
  Stopping = 'Stopping'  # 11
  Saving = 'Saving'  # 12
  Restoring = 'Restoring'  # 13
  TeleportingPausedVM = 'TeleportingPausedVM'  # 14
  TeleportingIn = 'TeleportingIn'  # 15
  FaultTolerantSyncing = 'FaultTolerantSyncing'  # 16
  DeletingSnapshotOnline = 'DeletingSnapshotOnline'  # 17
  DeletingSnapshotPaused = 'DeletingSnapshotPaused'  # 18
  OnlineSnapshotting = 'OnlineSnapshotting'  # 19
  LastOnline = 'LastOnline'  # 19
  RestoringSnapshot = 'RestoringSnapshot'  # 20
  DeletingSnapshot = 'DeletingSnapshot'  # 21
  SettingUp = 'SettingUp'  # 22
  Snapshotting = 'Snapshotting'  # 23
  LastTransient = 'LastTransient'  # 23


class CleanupMode:
  UnregisterOnly = 'UnregisterOnly'  # 1
  DetachAllReturnNone = 'DetachAllReturnNone'  # 2
  DetachAllReturnHardDisksOnly = 'DetachAllReturnHardDisksOnly'  # 3
  Full = 'Full'  # 4


class NetworkAttachmentType:
  Null = 'Null'  # 0
  NAT = 'NAT'  # 1
  Bridged = 'Bridged'  # 2
  Internal = 'Internal'  # 3
  HostOnly = 'HostOnly'  # 4
  Generic = 'Generic'  # 5
  NATNetwork = 'NATNetwork'  # 6


class NetworkAdapterType:
  Null = 'Null'  # 0
  Am79C970A = 'Am79C970A'  # 1
  Am79C973 = 'Am79C973'  # 2
  I82540EM = 'I82540EM'  # 3
  I82543GC = 'I82543GC'  # 4
  I82545EM = 'I82545EM'  # 5
  Virtio = 'Virtio'  # 6


class MediumState:
  NotCreated = 'NotCreated'  # 0
  Created = 'Created'  # 1
  LockedRead = 'LockedRead'  # 2
  LockedWrite = 'LockedWrite'  # 3
  Inaccessible = 'Inaccessible'  # 4
  Creating = 'Creating'  # 5
  Deleting = 'Deleting'  # 6


class AccessMode:
  ReadOnly = 'ReadOnly'  # 1
  ReadWrite = 'ReadWrite'  # 2


class MediumVariant:
  Standard = 'Standard'  # 0
  VmdkSplit2G = 'VmdkSplit2G'  # 1
  VmdkRawDisk = 'VmdkRawDisk'  # 2
  VmdkStreamOptimized = 'VmdkStreamOptimized'  # 4
  VmdkESX = 'VmdkESX'  # 8
  VdiZeroExpand = 'VdiZeroExpand'  # 256
  Fixed = 'Fixed'  # 65536
  Diff = 'Diff'  # 131072
  NoCreateDir = 'NoCreateDir'  # 1073741824


class StorageBus:
  Null = 'Null'  # 0
  IDE = 'IDE'  # 1
  SATA = 'SATA'  # 2
  SCSI = 'SCSI'  # 3
  Floppy = 'Floppy'  # 4
  SAS = 'SAS'  # 5
  USB = 'USB'  # 6
  PCIe = 'PCIe'  # 7


class LockType:
  Null = 'Null'  # 0
  Shared = 'Shared'  # 1
  Write = 'Write'  # 2
  VM = 'VM'  # 3
