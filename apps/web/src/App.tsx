import { Suspense, lazy, useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { LogOut, UploadCloud, PieChart, Bookmark, Columns3, ShieldCheck, UserCheck, X, Radar, FlaskConical, Activity } from 'lucide-react';
import { ManagerBook } from '@/features/manager-book/ManagerBook';
import { LoginPage } from '@/features/auth/LoginPage';
import { TradebookUploadModal } from '@/features/ledger';
import { WatchlistPage, BoardPage } from '@/features/research';
import { SuperAdminDashboard } from '@/features/super-admin';
import { useAuthStore, useIsAuthenticated } from '@/stores/authStore';
import { apiLogout, fetchClients, silentRefreshToken, type ClientSummary } from '@/lib/api';
import { DataFreshnessPill } from '@/components/DataFreshnessPill';
import { NavTabButton } from '@/components/NavTabButton';
import { AccountMenu } from '@/components/AccountMenu';
import { ThemeToggle } from '@/components/ThemeToggle';
import { LoadingBlock } from '@/components/QueryStates';

const ClientView = lazy(() => import('@/features/client/ClientView').then((m) => ({ default: m.ClientView })));
const ScreenerPage = lazy(() => import('@/features/screener/ScreenerPage'));
const SectorResearchPage = lazy(() => import('@/features/screener/SectorResearchPage'));
const OrbPage = lazy(() => import('@/features/orb').then((m) => ({ default: m.OrbPage })));

type TabType = 'admin' | 'portfolios' | 'watchlists' | 'board' | 'screener' | 'sectors' | 'orb';

export function App() {
  const isAuth = useIsAuthenticated();
  const {
    role,
    clientId: userClientId,
    impersonatedManagerId,
    impersonatedManagerName,
    setImpersonation,
    accessToken,
    clearToken,
  } = useAuthStore();

  const [selectedClientId, setSelectedClientId] = useState<string | null>(null);
  const [currentTab, setCurrentTab] = useState<TabType>(role === 'super_admin' ? 'admin' : 'portfolios');
  const [isUploadOpen, setIsUploadOpen] = useState(false);

  // The role is only known after sign-in; land each persona on its own home tab.
  useEffect(() => {
    setCurrentTab(role === 'super_admin' ? 'admin' : 'portfolios');
    setSelectedClientId(null);
  }, [role]);

  const refreshToken = sessionStorage.getItem('pi_rt') ?? '';

  // The access token lives in memory only, so a reload starts signed out. Renew it from the
  // saved refresh token before deciding to show the login page.
  const [booting, setBooting] = useState(() => !useAuthStore.getState().accessToken && !!sessionStorage.getItem('pi_rt'));
  useEffect(() => {
    if (booting) void silentRefreshToken().finally(() => setBooting(false));
  }, [booting]);

  const { data: clients } = useQuery<ClientSummary[]>({
    queryKey: ['clients'],
    queryFn: () => fetchClients(),
    enabled: isAuth && role !== 'client',
  });

  async function handleLogout() {
    try {
      await apiLogout(accessToken, refreshToken);
    } finally {
      sessionStorage.removeItem('pi_rt');
      clearToken();
      setSelectedClientId(null);
    }
  }

  if (!isAuth && booting) {
    return <LoadingBlock rows={3} label="Restoring session" />;
  }

  if (!isAuth) {
    return <LoginPage onLoginSuccess={() => {}} />;
  }

  // Client persona: directly locked to their own portfolio
  if (role === 'client' && userClientId) {
    return (
      <div className="min-h-screen flex flex-col bg-canvas text-ink">
        <header className="sticky top-0 z-30 bg-paper/85 backdrop-blur-md border-b border-hairline">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-ink text-paper flex items-center justify-center font-bold text-sm">PI</div>
              <span className="font-bold tracking-tight text-base text-ink">Investor Portal</span>
            </div>
            <div className="flex items-center gap-2">
              <ThemeToggle />
              <AccountMenu onSignOut={handleLogout} />
              <button onClick={handleLogout} className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-canvas border border-hairline hover:bg-paper text-xs">
                <LogOut className="w-3.5 h-3.5" /> Sign out
              </button>
            </div>
          </div>
        </header>
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <Suspense fallback={<LoadingBlock rows={6} label="Loading portfolio" />}>
            <ClientView clientId={userClientId} onBack={() => {}} />
          </Suspense>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col bg-canvas text-ink">
      {/* Impersonation Banner for Super-Admin */}
      {impersonatedManagerId && (
        <div className="bg-positive/10 border-b border-positive/20 px-4 py-1.5 text-xs flex items-center justify-between text-ink">
          <div className="flex items-center gap-2 max-w-7xl mx-auto w-full">
            <UserCheck className="w-4 h-4 text-positive" />
            <span>Viewing platform as: <strong>{impersonatedManagerName || 'Selected Manager'}</strong></span>
            <button
              onClick={() => setImpersonation(null, null)}
              className="ml-auto inline-flex items-center gap-1 px-2 py-0.5 rounded bg-paper border border-hairline hover:bg-canvas text-subtle hover:text-ink font-semibold"
            >
              <X className="w-3 h-3" /> Exit Impersonation
            </button>
          </div>
        </div>
      )}

      {/* Top Navbar */}
      <header className="sticky top-0 z-30 bg-paper/85 backdrop-blur-md border-b border-hairline">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <div
              className="flex items-center gap-3 cursor-pointer"
              onClick={() => { setSelectedClientId(null); setCurrentTab(role === 'super_admin' ? 'admin' : 'portfolios'); }}
            >
              <div className="w-8 h-8 rounded-lg bg-ink text-paper flex items-center justify-center font-bold text-sm">PI</div>
              <span className="font-bold tracking-tight text-base text-ink hidden sm:inline">Portfolio Intelligence</span>
            </div>

            <nav className="flex items-center gap-1 bg-canvas p-1 rounded-xl border border-hairline text-xs font-semibold">
              {role === 'super_admin' && (
                <button
                  onClick={() => { setCurrentTab('admin'); setSelectedClientId(null); }}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-colors ${
                    currentTab === 'admin' ? 'bg-paper text-ink shadow-sm' : 'text-subtle hover:text-ink'
                  }`}
                >
                  <ShieldCheck className="w-3.5 h-3.5 text-positive" /> Platform Hub
                </button>
              )}
              <button
                onClick={() => { setCurrentTab('portfolios'); setSelectedClientId(null); }}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-colors ${
                  currentTab === 'portfolios' ? 'bg-paper text-ink shadow-sm' : 'text-subtle hover:text-ink'
                }`}
              >
                <PieChart className="w-3.5 h-3.5" /> Portfolios
              </button>
              <button
                onClick={() => setCurrentTab('watchlists')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-colors ${
                  currentTab === 'watchlists' ? 'bg-paper text-ink shadow-sm' : 'text-subtle hover:text-ink'
                }`}
              >
                <Bookmark className="w-3.5 h-3.5" /> Watchlists
              </button>
              <button
                onClick={() => setCurrentTab('board')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-colors ${
                  currentTab === 'board' ? 'bg-paper text-ink shadow-sm' : 'text-subtle hover:text-ink'
                }`}
              >
                <Columns3 className="w-3.5 h-3.5" /> Board
              </button>
              <NavTabButton
                active={currentTab === 'screener'}
                onClick={() => setCurrentTab('screener')}
                icon={<Radar className="w-3.5 h-3.5" aria-hidden />}
                label="Screener"
              />
              <NavTabButton
                active={currentTab === 'sectors'}
                onClick={() => setCurrentTab('sectors')}
                icon={<FlaskConical className="w-3.5 h-3.5" aria-hidden />}
                label="Sector R&D"
              />
              <NavTabButton
                active={currentTab === 'orb'}
                onClick={() => setCurrentTab('orb')}
                icon={<Activity className="w-3.5 h-3.5" aria-hidden />}
                label="ORB"
              />
            </nav>
          </div>

          <div className="flex items-center gap-3 text-xs font-medium text-subtle">
            <button
              onClick={() => setIsUploadOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-ink text-paper hover:bg-ink/90 font-semibold transition-colors"
            >
              <UploadCloud className="w-3.5 h-3.5" /> Upload tradebook
            </button>
            <DataFreshnessPill />
            <ThemeToggle />
              <AccountMenu onSignOut={handleLogout} />
            <button
              onClick={handleLogout}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-canvas border border-hairline hover:bg-paper transition-colors"
              title="Sign out"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {currentTab === 'admin' && (
          <SuperAdminDashboard
            onImpersonateManager={(mgrId, mgrName) => {
              setImpersonation(mgrId, mgrName);
              setCurrentTab('portfolios');
            }}
          />
        )}
        {currentTab === 'portfolios' && (
          selectedClientId ? (
            <Suspense fallback={<LoadingBlock rows={6} label="Loading client" />}>
              <ClientView clientId={selectedClientId} onBack={() => setSelectedClientId(null)} />
            </Suspense>
          ) : (
            <ManagerBook onSelectClient={(id) => setSelectedClientId(id)} />
          )
        )}
        {currentTab === 'watchlists' && <WatchlistPage />}
        {currentTab === 'board' && <BoardPage />}
        <Suspense fallback={<LoadingBlock rows={6} label="Loading page" />}>
          {currentTab === 'screener' && <ScreenerPage />}
          {currentTab === 'sectors' && <SectorResearchPage />}
          {currentTab === 'orb' && <OrbPage />}
        </Suspense>
      </main>

      <footer className="border-t border-hairline py-6 text-center text-xs text-subtle">
        Portfolio Intelligence v2 · Modular Monolith Engine · Strictly Adhering to Domain Rules R1–R18
      </footer>

      <TradebookUploadModal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        clients={clients || []}
        defaultClientId={selectedClientId}
      />
    </div>
  );
}
export default App;
