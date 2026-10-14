import { useRouter } from 'next/navigation';
import { useLocale } from 'next-intl';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

export default function LanguageSwitcher() {
  const router = useRouter();
  const currentLocale = useLocale();

  const switchLocale = (newLocale: string) => {
    const pathname = window.location.pathname;

    // 現在のロケール（'ja'または'en'）を新しいロケールに置換
    const newPath = pathname.replace(
      new RegExp(`\\b(${currentLocale})\\b`, 'g'),
      newLocale
    ).slice(10);

    router.push(newPath);
  };

  return (
    <div className="flex justify-end w-full">
      <Select value={currentLocale} onValueChange={switchLocale}>
        <SelectTrigger
          className="w-[90px] h-8 bg-indigo-800 text-white text-sm border-none shadow-none hover:bg-indigo-700"
        >
          <SelectValue placeholder="Lang" />
        </SelectTrigger>
        <SelectContent className="bg-indigo-800 text-white text-xs border-none">
          <SelectItem value="en" className="hover:bg-indigo-800 text-xs">
            English
          </SelectItem>
          <SelectItem value="ja" className="hover:bg-indigo-800 text-xs">
            日本語
          </SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}