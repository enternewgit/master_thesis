"use client";
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { ReactNode, useState } from 'react';


interface ProviderProps {
    children: ReactNode;
}

const MyProvider = ({ children }: ProviderProps) => {
    const [queryClient] = useState(() => new QueryClient());

    return (
            <QueryClientProvider client={queryClient}>
                {children}
                 <ReactQueryDevtools initialIsOpen={false} /> {/*ここでReactQuery用のDevtoolsを使う設定 */}
            </QueryClientProvider>
    );
};

export default MyProvider;