import React from 'react';

function ErrorMessage({ message }: { message: string }) {
  return (
    <div className="bg-red-900 text-red-100 p-3 rounded-md mb-4">
      <strong>Error:</strong> {message}
    </div>
  );
}

export default ErrorMessage;
