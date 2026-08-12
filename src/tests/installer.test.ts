import { InstallerStateMachine } from '../services/InstallerStateMachine';
import { formatPartitionDevice, BrowserMockSystemBackend, isBrowserDevelopment } from '../services/SystemBackend';
import { StartupResolver, InstallerSessionStore } from '../services/StartupResolver';
import { COUNTRIES_DATA } from '../data/countries';

function assert(condition: boolean, message: string) {
  if (!condition) {
    console.error(`❌ ASSERTION FAILED: ${message}`);
    throw new Error(`ASSERTION FAILED: ${message}`);
  } else {
    console.log(`✅ PASS: ${message}`);
  }
}

async function runInstallerTests() {
  console.log('==================================================');
  console.log('RUNNING WINDROID OS INSTALLER AUTOMATED TEST SUITE');
  console.log('==================================================');

  // ----------------------------------------------------
  // TEST 1: InstallerStateMachine Phase 1 Transitions
  // ----------------------------------------------------
  console.log('\n--- Test 1: InstallerStateMachine Phase 1 Transitions ---');
  const sm1 = new InstallerStateMachine('installation', 'language');
  let snap = sm1.getSnapshot();
  assert(snap.phase === 'installation' && snap.step === 'language', 'Initial step is Phase 1 language');
  assert(!snap.canGoBack, 'Cannot go back from step 1 (language)');

  // Language -> Target Disk
  sm1.dispatch({ type: 'SELECT_LANGUAGE', payload: { language: 'en_US.UTF-8' } });
  assert(sm1.goNext(), 'Can navigate from language to target-disk');
  snap = sm1.getSnapshot();
  assert(snap.phase === 'installation' && snap.step === 'target-disk', 'Step is now target-disk');
  assert(snap.canGoBack, 'Can go back from target-disk');

  // Target Disk -> Ready
  sm1.dispatch({ type: 'SELECT_DISK', payload: { selectedDiskDevice: '/dev/sda' } });
  assert(sm1.goNext(), 'Can navigate from target-disk to ready');
  snap = sm1.getSnapshot();
  assert(snap.phase === 'installation' && snap.step === 'ready', 'Step is now ready');

  // Start Installation Action -> Installing
  sm1.dispatch({ type: 'START_INSTALLATION' });
  snap = sm1.getSnapshot();
  assert(snap.phase === 'installation' && snap.step === 'installing', 'Step is now installing');
  assert(!snap.canGoBack, 'Cannot go back while installing');

  // Progress update & complete
  sm1.dispatch({
    type: 'UPDATE_INSTALL_PROGRESS',
    payload: {
      status: {
        status: 'completed',
        stage: 'completed',
        stageDescription: 'Done',
        progress: 100,
        error: null,
        canInstall: false,
        runtimeMode: 'browser-development',
        bootMode: 'uefi'
      }
    }
  });
  sm1.dispatch({ type: 'INSTALLATION_COMPLETE' });
  snap = sm1.getSnapshot();
  assert(snap.phase === 'installation' && snap.step === 'complete', 'Step is now complete');

  // ----------------------------------------------------
  // TEST 2: InstallerStateMachine Phase 2 (OOBE) Transitions
  // ----------------------------------------------------
  console.log('\n--- Test 2: InstallerStateMachine Phase 2 OOBE Transitions ---');
  sm1.dispatch({ type: 'RESTART_COMPLETED' });
  snap = sm1.getSnapshot();
  assert(snap.phase === 'oobe' && snap.step === 'region', 'Transitioned to Phase 2 OOBE region step');

  // Region -> Keyboard
  sm1.dispatch({ type: 'SELECT_REGION', payload: { countryId: 'US' } });
  assert(sm1.goNext(), 'Can navigate from region to keyboard');
  snap = sm1.getSnapshot();
  assert(snap.phase === 'oobe' && snap.step === 'keyboard', 'Step is now keyboard');

  // Keyboard -> User
  sm1.dispatch({ type: 'SELECT_KEYBOARD', payload: { keyboard: 'us' } });
  assert(sm1.goNext(), 'Can navigate from keyboard to user');
  snap = sm1.getSnapshot();
  assert(snap.phase === 'oobe' && snap.step === 'user', 'Step is now user');

  // User -> Personalization
  sm1.dispatch({ type: 'CREATE_USER', payload: { username: 'alex', fullName: 'Alex User' } });
  assert(sm1.goNext(), 'Can navigate from user to personalization with valid username');
  snap = sm1.getSnapshot();
  assert(snap.phase === 'oobe' && snap.step === 'personalization', 'Step is now personalization');

  // Personalization -> Finalizing
  sm1.dispatch({ type: 'UPDATE_PERSONALIZATION', payload: { deviceName: 'Alex-PC' } });
  assert(sm1.goNext(), 'Can navigate from personalization to finalizing');
  snap = sm1.getSnapshot();
  assert(snap.phase === 'oobe' && snap.step === 'finalizing', 'Step is now finalizing');

  // Finalizing -> Desktop
  sm1.dispatch({ type: 'FINALIZE_OOBE' });
  snap = sm1.getSnapshot();
  assert(snap.phase === 'oobe' && snap.step === 'desktop', 'Step is now desktop');

  // ----------------------------------------------------
  // TEST 3: Back Button Navigation & Scenario Test
  // ----------------------------------------------------
  console.log('\n--- Test 3: Back Navigation & Scenario Test ---');
  const smBack = new InstallerStateMachine('installation', 'language');
  smBack.dispatch({ type: 'SELECT_LANGUAGE', payload: { language: 'en_US.UTF-8' } });
  smBack.goNext(); // to target-disk
  smBack.dispatch({ type: 'SELECT_DISK', payload: { selectedDiskDevice: '/dev/sda' } });
  smBack.goNext(); // to ready

  // Back from ready -> target-disk
  smBack.goBack();
  assert(smBack.getSnapshot().step === 'target-disk', 'Back from ready navigates to target-disk');

  // Back from target-disk -> language
  smBack.goBack();
  assert(smBack.getSnapshot().step === 'language', 'Back from target-disk navigates to language');

  // Next from language -> target-disk -> ready
  smBack.goNext();
  assert(smBack.getSnapshot().step === 'target-disk', 'Next from language navigates back to target-disk');
  smBack.goNext();
  assert(smBack.getSnapshot().step === 'ready', 'Next from target-disk navigates back to ready');

  // ----------------------------------------------------
  // TEST 4: Username Regex Validation
  // ----------------------------------------------------
  console.log('\n--- Test 4: Username Regex Validation ---');
  const validUsernames = ['windroid', 'alex_123', '_admin', 'user-name', 'a1'];
  const invalidUsernames = ['123user', 'Alex', 'user@domain', 'user name', 'admin!', ''];

  const usernameRegex = /^[a-z_][a-z0-9_-]*$/;

  for (const u of validUsernames) {
    assert(usernameRegex.test(u), `Valid username accepted: "${u}"`);
  }
  for (const u of invalidUsernames) {
    assert(!usernameRegex.test(u), `Invalid username rejected: "${u}"`);
  }

  // ----------------------------------------------------
  // TEST 5: Partition Naming Helper
  // ----------------------------------------------------
  console.log('\n--- Test 5: Partition Naming Helper ---');
  assert(formatPartitionDevice('/dev/sda', 1) === '/dev/sda1', 'sda -> /dev/sda1');
  assert(formatPartitionDevice('/dev/sda', 2) === '/dev/sda2', 'sda -> /dev/sda2');
  assert(formatPartitionDevice('/dev/nvme0n1', 1) === '/dev/nvme0n1p1', 'nvme0n1 -> /dev/nvme0n1p1');
  assert(formatPartitionDevice('/dev/nvme0n1', 2) === '/dev/nvme0n1p2', 'nvme0n1 -> /dev/nvme0n1p2');
  assert(formatPartitionDevice('/dev/mmcblk0', 1) === '/dev/mmcblk0p1', 'mmcblk0 -> /dev/mmcblk0p1');

  // ----------------------------------------------------
  // TEST 6: Country Data Uniqueness
  // ----------------------------------------------------
  console.log('\n--- Test 6: Country Data Uniqueness ---');
  const countryIds = COUNTRIES_DATA.map((c) => c.id);
  const uniqueCountryIds = new Set(countryIds);
  assert(countryIds.length === uniqueCountryIds.size, 'All country IDs in COUNTRIES_DATA are unique');

  const countryNames = COUNTRIES_DATA.map((c) => c.name);
  const uniqueCountryNames = new Set(countryNames);
  assert(countryNames.length === uniqueCountryNames.size, 'All country names in COUNTRIES_DATA are unique');

  // ----------------------------------------------------
  // TEST 7: Live Media Protection & Disk Selection
  // ----------------------------------------------------
  console.log('\n--- Test 7: Live Media Protection ---');
  const mockBackend = new BrowserMockSystemBackend();
  const disksRes = await mockBackend.getInstallerDisks();
  assert(disksRes.disks.length > 0, 'Disks discovered via backend');
  
  const liveDisk = disksRes.disks.find((d) => d.isLiveMedia);
  assert(!!liveDisk, 'Live media drive identified');
  assert(liveDisk?.protected === true, 'Live media drive marked protected');
  
  const eligible = disksRes.eligibleDisks;
  assert(!eligible.some((d) => d.isLiveMedia), 'Eligible disks exclude live media');

  // ----------------------------------------------------
  // TEST 8: Plan Generation & Validation
  // ----------------------------------------------------
  console.log('\n--- Test 8: Plan Generation & Validation ---');
  const planRes = await mockBackend.generateInstallerPlan('/dev/sda', 'erase_disk', { username: 'windroid' }, { language: 'en_US.UTF-8' });
  assert(planRes.success && !!planRes.plan, 'Plan generated successfully');
  assert(planRes.plan.partitions.length >= 2, 'Plan includes boot and root partitions');

  const valRes = await mockBackend.validateInstallerPlan(planRes.plan);
  assert(valRes.valid, 'Plan validation succeeds');

  const authRes = await mockBackend.authorizeInstallerPlan(planRes.plan);
  assert(authRes.success && !!authRes.authToken, 'Plan authorization produces valid token');

  // ----------------------------------------------------
  // TEST 9: Runtime Environment Resolution
  // ----------------------------------------------------
  console.log('\n--- Test 9: Runtime Environment Resolution ---');
  assert(isBrowserDevelopment(), 'Browser development resolver identifies sandbox/preview mode');

  // ----------------------------------------------------
  // TEST 10: StartupResolver & InstallerSessionStore Persistence
  // ----------------------------------------------------
  console.log('\n--- Test 10: StartupResolver & InstallerSessionStore Persistence ---');
  InstallerSessionStore.clearSession();
  assert(InstallerSessionStore.getSession() === null, 'InstallerSessionStore cleared successfully');

  InstallerSessionStore.markInstallationCompleted({
    targetDisk: '/dev/sda',
    userConfig: { username: 'testuser', fullName: 'Test User', deviceName: 'Test-PC' }
  });

  const session = InstallerSessionStore.getSession();
  assert(session?.installationCompleted === true, 'installationCompleted flag saved in installer-session-v1');
  assert(session?.oobeCompleted === false, 'oobeCompleted flag is false prior to OOBE finish');
  assert(session?.targetDisk === '/dev/sda', 'Target disk correctly recorded in installer-session-v1');

  const startupRoute = await StartupResolver.resolveStartupRoute();
  assert(startupRoute.runtimeMode === 'installer', 'StartupResolver routes to installer when installation completed but OOBE pending');
  assert(startupRoute.initialPhase === 'oobe', 'StartupResolver sets initialPhase to oobe');

  InstallerSessionStore.markOobeCompleted();
  const sessionAfterOobe = InstallerSessionStore.getSession();
  assert(sessionAfterOobe?.oobeCompleted === true, 'oobeCompleted marked true in installer-session-v1');

  const routeAfterOobe = await StartupResolver.resolveStartupRoute();
  assert(routeAfterOobe.runtimeMode === 'installed', 'StartupResolver routes to installed desktop after OOBE completes');

  InstallerSessionStore.clearSession();

  console.log('\n==================================================');
  console.log('ALL INSTALLER AUTOMATED TESTS COMPLETED SUCCESSFULLY');
  console.log('==================================================\n');
}

runInstallerTests().catch((err) => {
  console.error('TEST SUITE FAILED:', err);
  process.exit(1);
});
