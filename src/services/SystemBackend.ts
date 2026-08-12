import { WindroidSystemBridge } from './WindroidSystemBridge';
import { RuntimeEnvironmentResolver } from './RuntimeEnvironmentResolver';
import {
  InstallerDisk,
  InstallerStatus,
  InstallationPlan,
  BootMode,
  InstallationMode,
  UserConfig,
  LocaleConfig,
  GetInstallerDisksResponse,
  NativeInstallerStateResponse
} from '../types/installer';
import { RuntimeMode } from '../types/user-session';
import { PowerAction } from '../types/hardware';

export function formatPartitionDevice(targetDisk: string, partNumber: number): string {
  if (!targetDisk) return '';
  const lastChar = targetDisk.slice(-1);
  if (/\d/.test(lastChar)) {
    return `${targetDisk}p${partNumber}`;
  }
  return `${targetDisk}${partNumber}`;
}

export function isBrowserDevelopment(): boolean {
  return RuntimeEnvironmentResolver.isBrowserDevelopment();
}

export interface SystemBackend {
  checkNativeBridge(forceRecheck?: boolean): Promise<boolean>;
  getNativeInstallerState(): Promise<NativeInstallerStateResponse>;
  completeOobe(data: {
    username: string;
    password?: string;
    fullName?: string;
    deviceName?: string;
    timezone?: string;
    keyboard?: string;
    language?: string;
  }): Promise<{ success: boolean; username?: string; error?: string }>;
  getInstallerStatus(): Promise<InstallerStatus>;
  getInstallerDisks(): Promise<GetInstallerDisksResponse>;
  getInstallerBootMode(): Promise<{ success: boolean; bootMode: BootMode }>;
  generateInstallerPlan(
    targetDisk: string,
    installationMode: InstallationMode,
    userConfig: Partial<UserConfig>,
    localeConfig: Partial<LocaleConfig>,
    customPartitions?: any[]
  ): Promise<{ success: boolean; plan: InstallationPlan; authToken?: string; errors: string[]; warnings: string[] }>;
  validateInstallerPlan(plan: InstallationPlan): Promise<{ success: boolean; valid: boolean; errors: string[]; warnings: string[] }>;
  authorizeInstallerPlan(plan: InstallationPlan): Promise<{ success: boolean; authToken?: string; plan?: InstallationPlan; errors?: string[] }>;
  executeInstallerPlan(plan: InstallationPlan, authToken?: string): Promise<{ success: boolean; status?: string; error?: string }>;
  executePowerAction(action: PowerAction): Promise<{ success: boolean; error?: string }>;
  createUser(data: { username: string; fullName?: string; password?: string; isAdmin?: boolean }): Promise<{ success: boolean; username?: string; error?: string }>;
  setTimezone(timezone: string): Promise<{ success: boolean; error?: string }>;
  setLocale(locale: string): Promise<{ success: boolean; error?: string }>;
  setKeyboardLayout(layout: string): Promise<{ success: boolean; error?: string }>;
  getRuntimeMode(): Promise<RuntimeMode>;
  subscribeInstallerProgress(onProgress: (status: InstallerStatus) => void): () => void;
}

export class NativeSystemBackend implements SystemBackend {
  private bridge = WindroidSystemBridge.getInstance();

  public async checkNativeBridge(forceRecheck?: boolean): Promise<boolean> {
    return await this.bridge.checkNativeBridge(forceRecheck);
  }

  public async getNativeInstallerState(): Promise<NativeInstallerStateResponse> {
    return await this.bridge.getNativeInstallerState();
  }

  public async completeOobe(data: {
    username: string;
    password?: string;
    fullName?: string;
    deviceName?: string;
    timezone?: string;
    keyboard?: string;
    language?: string;
  }): Promise<{ success: boolean; username?: string; error?: string }> {
    return await this.bridge.completeOobe(data);
  }

  public async getInstallerStatus(): Promise<InstallerStatus> {
    return await this.bridge.getInstallerStatus();
  }

  public async getInstallerDisks(): Promise<GetInstallerDisksResponse> {
    return await this.bridge.getInstallerDisks();
  }

  public async getInstallerBootMode(): Promise<{ success: boolean; bootMode: BootMode }> {
    return await this.bridge.getInstallerBootMode();
  }

  public async generateInstallerPlan(
    targetDisk: string,
    installationMode: InstallationMode,
    userConfig: Partial<UserConfig>,
    localeConfig: Partial<LocaleConfig>,
    customPartitions?: any[]
  ) {
    return await this.bridge.generateInstallerPlan(targetDisk, installationMode, userConfig, localeConfig, customPartitions);
  }

  public async validateInstallerPlan(plan: InstallationPlan) {
    return await this.bridge.validateInstallerPlan(plan);
  }

  public async authorizeInstallerPlan(plan: InstallationPlan) {
    return await this.bridge.authorizeInstallerPlan(plan);
  }

  public async executeInstallerPlan(plan: InstallationPlan, authToken?: string) {
    return await this.bridge.executeInstallerPlan(plan, authToken);
  }

  public async executePowerAction(action: PowerAction) {
    return await this.bridge.executePowerAction(action);
  }

  public async createUser(data: { username: string; fullName?: string; password?: string; isAdmin?: boolean }) {
    return await this.bridge.createUser(data);
  }

  public async setTimezone(timezone: string) {
    return await this.bridge.setTimezone(timezone);
  }

  public async setLocale(locale: string) {
    return await this.bridge.setLocale(locale);
  }

  public async setKeyboardLayout(layout: string) {
    return await this.bridge.setKeyboardLayout(layout);
  }

  public async getRuntimeMode() {
    return await this.bridge.getRuntimeMode();
  }

  public subscribeInstallerProgress(onProgress: (status: InstallerStatus) => void): () => void {
    let active = true;
    const interval = setInterval(async () => {
      if (!active) return;
      try {
        const st = await this.getInstallerStatus();
        if (active) onProgress(st);
      } catch (_) {}
    }, 1000);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }
}

export class BrowserMockSystemBackend implements SystemBackend {
  private isExecuting: boolean = false;
  private mockStatus: InstallerStatus = {
    status: 'idle',
    stage: 'idle',
    stageDescription: 'Ready to install (Browser Preview Mode)',
    progress: 0,
    error: null,
    canInstall: true,
    runtimeMode: 'browser-development',
    bootMode: 'uefi'
  };

  private progressListeners: Set<(status: InstallerStatus) => void> = new Set();
  private progressTimer: NodeJS.Timeout | null = null;

  public async checkNativeBridge(): Promise<boolean> {
    return false;
  }

  public async getNativeInstallerState(): Promise<NativeInstallerStateResponse> {
    return {
      success: true,
      version: 'windroid-installer-state-v1',
      state: 'INSTALLER',
      runtimeMode: 'browser-development'
    };
  }

  public async completeOobe(data: {
    username: string;
    password?: string;
    fullName?: string;
    deviceName?: string;
    timezone?: string;
    keyboard?: string;
    language?: string;
  }): Promise<{ success: boolean; username?: string; error?: string }> {
    return { success: true, username: data.username };
  }

  public async getInstallerStatus(): Promise<InstallerStatus> {
    return { ...this.mockStatus };
  }

  public async getInstallerDisks(): Promise<GetInstallerDisksResponse> {
    const primaryDisk: InstallerDisk = {
      device: '/dev/sda',
      model: 'Virtual Storage Device (64 GB NVMe)',
      vendor: 'Windroid Virtual',
      serial: 'WND-VIRT-64G-001',
      sizeBytes: 64 * 1024 * 1024 * 1024,
      transport: 'nvme',
      removable: false,
      rotational: false,
      readOnly: false,
      systemDisk: false,
      isLiveMedia: false,
      protected: false,
      isMock: true,
      partitions: [
        {
          device: '/dev/sda1',
          number: 1,
          sizeBytes: 512 * 1024 * 1024,
          filesystem: 'fat32',
          label: 'BOOT',
          uuid: 'mock-efi-uuid-1111',
          mountPoint: '/boot/efi',
          partitionType: 'c12a7328-f81f-11d2-ba4b-00a0c93ec93b',
          bootable: true,
          flags: ['boot', 'esp']
        },
        {
          device: '/dev/sda2',
          number: 2,
          sizeBytes: 63.5 * 1024 * 1024 * 1024,
          filesystem: 'ext4',
          label: 'WindroidOS',
          uuid: 'mock-root-uuid-2222',
          mountPoint: '/',
          partitionType: '0fc63daf-8483-4772-8e79-3d69d8477de4',
          bootable: false
        }
      ]
    };

    const liveUsbDisk: InstallerDisk = {
      device: '/dev/sdb',
      model: 'Windroid Live USB Drive (16 GB)',
      vendor: 'SanDisk USB',
      serial: 'LIVE-USB-MEDIA-999',
      sizeBytes: 16 * 1024 * 1024 * 1024,
      transport: 'usb',
      removable: true,
      rotational: false,
      readOnly: true,
      systemDisk: true,
      isLiveMedia: true,
      protected: true,
      protectionReason: 'Live installation media is protected from overwrite',
      isMock: true,
      partitions: []
    };

    return {
      success: true,
      disks: [primaryDisk, liveUsbDisk],
      eligibleDisks: [primaryDisk],
      excludedDevices: [
        {
          path: '/dev/sdb',
          reason: 'Live installation source media',
          sizeBytes: 16 * 1024 * 1024 * 1024
        }
      ],
      liveMediaDevice: '/dev/sdb'
    };
  }

  public async getInstallerBootMode(): Promise<{ success: boolean; bootMode: BootMode }> {
    return { success: true, bootMode: 'uefi' };
  }

  public async generateInstallerPlan(
    targetDisk: string,
    installationMode: InstallationMode,
    userConfig: Partial<UserConfig>,
    localeConfig: Partial<LocaleConfig>
  ) {
    if (!targetDisk) {
      return {
        success: false,
        plan: null as any,
        authToken: '',
        errors: ['Target disk selection is required.'],
        warnings: []
      };
    }

    if (targetDisk === '/dev/sdb') {
      return {
        success: false,
        plan: null as any,
        authToken: '',
        errors: ['Target disk is live installation media and cannot be overwritten.'],
        warnings: []
      };
    }

    const mockPlan: InstallationPlan = {
      version: '1.0',
      targetDisk,
      bootMode: 'uefi',
      installationMode,
      partitions: [
        {
          device: formatPartitionDevice(targetDisk, 1),
          sizeBytes: 512 * 1024 * 1024,
          filesystem: 'fat32',
          mountPoint: '/boot/efi',
          label: 'BOOT',
          flags: ['boot', 'esp']
        },
        {
          device: formatPartitionDevice(targetDisk, 2),
          sizeBytes: 63.5 * 1024 * 1024 * 1024,
          filesystem: 'ext4',
          mountPoint: '/',
          label: 'WindroidOS'
        }
      ],
      userConfig: {
        username: userConfig.username || 'windroid',
        fullName: userConfig.fullName || 'Windroid User',
        password: userConfig.password || '',
        deviceName: userConfig.deviceName || 'windroid-pc',
        requirePassword: userConfig.requirePassword ?? true
      },
      localeConfig: {
        language: localeConfig.language || 'en_US.UTF-8',
        keyboard: localeConfig.keyboard || 'us',
        timezone: localeConfig.timezone || 'UTC'
      },
      bootloaderConfig: {
        targetDevice: targetDisk,
        type: 'grub-efi'
      }
    };

    return {
      success: true,
      plan: mockPlan,
      authToken: 'mock-dev-token-abc12345',
      errors: [],
      warnings: []
    };
  }

  public async validateInstallerPlan(plan: InstallationPlan) {
    if (plan.targetDisk === '/dev/sdb') {
      return {
        success: false,
        valid: false,
        errors: ['Target disk /dev/sdb is live media and protected.'],
        warnings: []
      };
    }
    return { success: true, valid: true, errors: [], warnings: [] };
  }

  public async authorizeInstallerPlan(plan: InstallationPlan) {
    if (plan.targetDisk === '/dev/sdb') {
      return { success: false, errors: ['Target disk /dev/sdb is live media and protected.'] };
    }
    return { success: true, authToken: 'mock-dev-token-abc12345', plan };
  }

  public async executeInstallerPlan(plan: InstallationPlan, authToken?: string) {
    if (this.isExecuting) {
      return { success: false, error: 'Installation is already in progress.' };
    }

    if (plan.targetDisk === '/dev/sdb') {
      return { success: false, error: 'Target disk /dev/sdb is protected live installation media.' };
    }

    this.isExecuting = true;
    this.mockStatus = {
      status: 'in_progress',
      stage: 'preparing_disk',
      stageDescription: 'Preparing target disk layout...',
      progress: 5,
      error: null,
      canInstall: false,
      runtimeMode: 'browser-development',
      bootMode: 'uefi'
    };
    this.notifyListeners();

    if (this.progressTimer) clearInterval(this.progressTimer);

    const steps: Array<{ stage: any; desc: string; progress: number }> = [
      { stage: 'preparing_disk', desc: 'Preparing GPT partition table...', progress: 10 },
      { stage: 'creating_partitions', desc: 'Creating EFI boot & ext4 root partitions...', progress: 25 },
      { stage: 'formatting_filesystems', desc: 'Formatting target ext4 filesystem...', progress: 40 },
      { stage: 'copying_system', desc: 'Copying Windroid OS image & system modules...', progress: 60 },
      { stage: 'configuring_system', desc: 'Applying system settings & regional configuration...', progress: 80 },
      { stage: 'installing_bootloader', desc: 'Installing GRUB EFI bootloader...', progress: 95 },
      { stage: 'completed', desc: 'Windroid OS installation complete!', progress: 100 }
    ];

    let stepIdx = 0;
    this.progressTimer = setInterval(() => {
      if (stepIdx < steps.length) {
        const item = steps[stepIdx];
        this.mockStatus = {
          ...this.mockStatus,
          status: item.progress === 100 ? 'completed' : 'in_progress',
          stage: item.stage,
          stageDescription: item.desc,
          progress: item.progress
        };
        this.notifyListeners();
        stepIdx++;
      } else {
        if (this.progressTimer) clearInterval(this.progressTimer);
        this.progressTimer = null;
        this.isExecuting = false;
      }
    }, 800);

    return { success: true, status: 'started' };
  }

  public async executePowerAction(action: PowerAction) {
    console.log(`[BrowserMockSystemBackend] Executed power action: ${action}`);
    return { success: true };
  }

  public async createUser(data: { username: string; fullName?: string; password?: string }) {
    try {
      const existing = localStorage.getItem('windroid_user_accounts');
      const accounts = existing ? JSON.parse(existing) : [];
      
      // Avoid duplicate accounts on repeated submissions
      const idx = accounts.findIndex((a: any) => a.username === data.username);
      const acc = {
        username: data.username,
        fullName: data.fullName || data.username,
        isAdmin: true,
        uid: 1000,
        gid: 1000
      };

      if (idx >= 0) {
        accounts[idx] = acc;
      } else {
        accounts.push(acc);
      }

      localStorage.setItem('windroid_user_accounts', JSON.stringify(accounts));
      localStorage.setItem('windroid_current_user', data.username);
    } catch (_) {}
    return { success: true, username: data.username };
  }

  public async setTimezone(timezone: string) {
    try {
      localStorage.setItem('windroid_timezone', timezone);
    } catch (_) {}
    return { success: true };
  }

  public async setLocale(locale: string) {
    try {
      localStorage.setItem('windroid_locale', locale);
    } catch (_) {}
    return { success: true };
  }

  public async setKeyboardLayout(layout: string) {
    try {
      localStorage.setItem('windroid_keyboard', layout);
    } catch (_) {}
    return { success: true };
  }

  public async getRuntimeMode(): Promise<RuntimeMode> {
    return 'browser-development';
  }

  public subscribeInstallerProgress(onProgress: (status: InstallerStatus) => void): () => void {
    this.progressListeners.add(onProgress);
    onProgress(this.mockStatus);

    return () => {
      this.progressListeners.delete(onProgress);
    };
  }

  private notifyListeners() {
    this.progressListeners.forEach(listener => listener({ ...this.mockStatus }));
  }
}

let activeBackendInstance: SystemBackend | null = null;

export async function initializeSystemBackend(): Promise<SystemBackend> {
  if (activeBackendInstance) return activeBackendInstance;

  if (isBrowserDevelopment()) {
    activeBackendInstance = new BrowserMockSystemBackend();
    return activeBackendInstance;
  }

  // In native production ISO environment, strictly use NativeSystemBackend.
  activeBackendInstance = new NativeSystemBackend();
  await activeBackendInstance.checkNativeBridge(true);
  return activeBackendInstance;
}

export function getSystemBackend(): SystemBackend {
  if (!activeBackendInstance) {
    if (isBrowserDevelopment()) {
      activeBackendInstance = new BrowserMockSystemBackend();
    } else {
      activeBackendInstance = new NativeSystemBackend();
    }
  }
  return activeBackendInstance;
}
