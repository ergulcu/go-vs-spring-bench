package bench;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import redis.clients.jedis.JedisPool;
import redis.clients.jedis.JedisPoolConfig;

/** STORE=valkey: Jedis bağlantı havuzu. PostgreSQL modundaki Hikari havuzuyla aynı boyut (20). */
@Configuration
@Profile("valkey")
public class ValkeyConfig {

    @Bean(destroyMethod = "close")
    public JedisPool jedisPool() throws Exception {
        JedisPoolConfig cfg = new JedisPoolConfig();
        cfg.setMaxTotal(20);
        cfg.setMaxIdle(20);
        cfg.setMinIdle(20);
        String host = System.getenv().getOrDefault("VALKEY_HOST", "bench-valkey");
        // Zaman aşımı 30 sn (varsayılan 2 sn): doygun Lua betiği kuyruğunda bekleyen istekler zaman aşımına düşmesin; go-redis tarafıyla aynı.
        JedisPool pool = new JedisPool(cfg, host, 6379, 30000);
        pool.preparePool(); // MinIdle kadar bağlantıyı baştan aç (Go tarafındaki MinIdleConns gibi)
        return pool;
    }
}
