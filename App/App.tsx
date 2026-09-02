import { StatusBar } from 'expo-status-bar';
import { StyleSheet, View } from 'react-native';

import HomeScreen from './src/screens/HomeScreen';

export default function App() {
  return (
    <View style={styles.app}>
      <StatusBar style="light" />
      <HomeScreen />
    </View>
  );
}

const styles = StyleSheet.create({
  app: {
    // The DISHA ground. HomeScreen paints its own background over this, so the
    // only place it shows is behind the safe area and during the first frame --
    // which is exactly where the old charcoal appeared as a mismatched band.
    flex: 1,
    backgroundColor: '#0b1620',
  },
});
