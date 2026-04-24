import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { useEffect } from 'react';
import { Toaster } from 'sonner';

import { SessionExpiredModal } from './components/auth/SessionExpiredModal';
import { ProtectedRoute } from './components/common/ProtectedRoute';
import { Dashboard } from './pages/Dashboard';
import { Login } from './pages/Login';
import { NotFound } from './pages/NotFound';
import { Register } from './pages/Register';
import { useAuthStore } from './store/authStore';

function AppRoutes() {
  // Placeholder while the auth interceptor wires the real session-expired flow.
  const showExpired = false;

  return (
    <>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route path="/" element={<Navigate to="/dashboard" />} />
        <Route path="*" element={<NotFound />} />
      </Routes>

      <SessionExpiredModal isOpen={showExpired} onClose={() => {}} />
      <Toaster position="top-right" />
    </>
  );
}

function App() {
  const { hydrate } = useAuthStore();

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}

export default App;
