export type BootMode = 'uefi' | 'bios';
export type InstallationMode = 'erase_disk' | 'manual';
export type InstallerStage =
  | 'idle'
  | 'preparing_disk'
  | 'creating_partitions'
  | 'formatting_filesystems'
  | 'mounting_target'
  | 'copying_system'
  | 'configuring_user'
  | 'configuring_system'
  | 'installing_bootloader'
  | 'finalizing'
  | 'completed'
  | 'failed';

export interface InstallerPartition {
  device: string;
  number: number;
  sizeBytes: number;
  filesystem: string;
  label: string;
  uuid: string;
  mountPoint: string;
  partitionType: string;
  bootable: boolean;
  flags?: string[];
}

export interface InstallerDisk {
  device: string;
  model: string;
  vendor: string;
  serial: string;
  sizeBytes: number;
  transport: string;
  removable: boolean;
  rotational: boolean;
  readOnly: boolean;
  systemDisk: boolean;
  isLiveMedia: boolean;
  protected?: boolean;
  protectionReason?: string;
  isMock?: boolean;
  partitions: InstallerPartition[];
}

export interface RawBlockDevice {
  path: string;
  name: string;
  type: string;
  sizeBytes: number;
  transport: string;
  removable: boolean;
  readOnly: boolean;
  model: string;
  serial: string;
  vendor: string;
  fstype?: string;
  mountPoint?: string;
}

export interface ExcludedDevice {
  path: string;
  reason: string;
  details?: string;
  sizeBytes?: number;
}

export interface GetInstallerDisksResponse {
  success: boolean;
  error?: string;
  disks: InstallerDisk[];
  rawBlockDevices?: RawBlockDevice[];
  eligibleDisks?: InstallerDisk[];
  excludedDevices?: ExcludedDevice[];
  liveMediaDevice?: string;
  rawKernelCmdline?: string;
  detectedWindroidMode?: string;
  diagnostics?: Record<string, any>;
}

export interface UserConfig {
  username: string;
  fullName: string;
  password?: string;
  deviceName: string;
  requirePassword: boolean;
}

export interface LocaleConfig {
  language: string;
  keyboard: string;
  timezone: string;
}

export interface PlannedPartition {
  device: string;
  sizeBytes: number;
  filesystem: string;
  mountPoint: string;
  label?: string;
  flags?: string[];
}

export interface InstallationPlan {
  version: string;
  targetDisk: string;
  bootMode: BootMode;
  installationMode: InstallationMode;
  partitions: PlannedPartition[];
  userConfig: UserConfig;
  localeConfig: LocaleConfig;
  bootloaderConfig: {
    targetDevice: string;
    type: 'grub-efi' | 'grub-pc';
  };
}

export interface InstallerStatus {
  status: 'idle' | 'in_progress' | 'completed' | 'failed';
  stage: InstallerStage;
  stageDescription: string;
  progress: number;
  error: string | null;
  canInstall: boolean;
  runtimeMode: 'live' | 'installed' | 'browser-development' | 'installer';
  bootMode: BootMode;
  liveMediaDevice?: string;
}

export type InstallerPhase = 'installation' | 'oobe';

export type InstallationStep =
  | 'language'
  | 'target-disk'
  | 'ready'
  | 'installing'
  | 'complete';

export type OobeStep =
  | 'region'
  | 'keyboard'
  | 'user'
  | 'personalization'
  | 'finalizing'
  | 'desktop';

export interface CountryItem {
  id: string;
  name: string;
  locale: string;
  timezone: string;
  keyboardLayouts?: string[];
}

export type NativeInstallerState =
  | 'INSTALLER'
  | 'INSTALLATION_IN_PROGRESS'
  | 'INSTALLATION_COMPLETE'
  | 'OOBE_PENDING'
  | 'OOBE_IN_PROGRESS'
  | 'OOBE_COMPLETE'
  | 'DESKTOP_READY'
  | 'FAILED';

export interface NativeInstallerStateResponse {
  success: boolean;
  version: string;
  state: NativeInstallerState;
  updatedAt?: string;
  targetDisk?: string;
  localeConfig?: Partial<LocaleConfig>;
  userConfig?: {
    username?: string;
    fullName?: string;
    deviceName?: string;
  };
  completedAt?: string;
  error?: string;
  runtimeMode?: string;
}


