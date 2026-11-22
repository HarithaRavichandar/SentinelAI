import React, { useEffect, useState } from 'react';
import { getHealth } from '../api';
import LoadingSpinner from './LoadingSpinner';
import ErrorMessage from './ErrorMessage';

function HealthView() {
  const [status, setStatus] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getHealth()
      .then((data) => {
        setStatus(data.status ?? 'unknown');
        setError(null);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorMessage message={error} />;

  return (
    <div className="container">
      <div className="card">
        <h1 className="text-2xl mb-4 font-medium">API Health</h1>
        <p>Status: <strong>{status}</strong></p>
      </div>
    </div>
  );
}

export default HealthView;
